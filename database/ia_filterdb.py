import logging
from struct import pack
import re
import base64
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError, BulkWriteError
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
from info import DATABASE_URI, DATABASE_NAME, COLLECTION_NAME, USE_CAPTION_FILTER

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

client = AsyncIOMotorClient(DATABASE_URI)
db = client[DATABASE_NAME]
instance = Instance.from_db(db)

@instance.register
class Media(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    file_type = fields.StrField(allow_none=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)

    class Meta:
        # 🔴 FIX: We commented this out to prevent the "IndexOptionsConflict" error.
        # Your bot will now use the existing index you created in MongoDB Atlas.
        # indexes = ('$file_name', )
        
        collection_name = COLLECTION_NAME


async def save_file(media):
    """Save file in database"""

    # TODO: Find better way to get same file_id for same media to avoid duplicates
    file_id, file_ref = unpack_new_file_id(media.file_id)
    file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
    try:
        file = Media(
            file_id=file_id,
            file_ref=file_ref,
            file_name=file_name,
            file_size=media.file_size,
            file_type=media.file_type,
            mime_type=media.mime_type,
            caption=media.caption.html if media.caption else None,
        )
    except ValidationError:
        logger.exception('Error occurred while saving file in database')
        return False, 2
    else:
        try:
            await file.commit()
        except DuplicateKeyError:      
            logger.warning(
                f'{getattr(media, "file_name", "NO_FILE")} is already saved in database'
            )
            return False, 0
        else:
            logger.info(f'{getattr(media, "file_name", "NO_FILE")} is saved to database')
            return True, 1

# -------------------------------------------------------------------
#  ✅ NEW: Batch Save Function for Fast Indexing
# -------------------------------------------------------------------
async def save_file_batch(items):
    """
    Saves a list of media objects to the database in one go.
    Optimized for high-speed indexing.
    """
    data_list = []
    
    for media in items:
        # Logic copied from save_file to process data
        file_id, file_ref = unpack_new_file_id(media.file_id)
        file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
        
        # Prepare the document as a raw dictionary
        # We use raw dicts because it's faster than creating Objects
        doc = {
            "_id": file_id, # Using file_id as the unique key
            "file_ref": file_ref,
            "file_name": file_name,
            "file_size": media.file_size,
            "file_type": media.file_type,
            "mime_type": media.mime_type,
            "caption": media.caption.html if media.caption else None,
        }
        data_list.append(doc)

    if not data_list:
        return 0

    try:
        # ordered=False is CRITICAL. 
        # It means: "If one file is a duplicate, skip it and KEEP SAVING the others."
        result = await Media.collection.insert_many(data_list, ordered=False)
        return len(result.inserted_ids)
    except BulkWriteError as e:
        # If duplicates exist, MongoDB raises a BulkWriteError.
        # We extract 'nInserted' to know how many new files were actually saved.
        return e.details['nInserted']
    except Exception as e:
        logger.error(f"Batch save error: {e}")
        return 0


async def get_search_results(query, file_type=None, max_results=7, offset=0, filter=False):
    """For given query return (results, next_offset)"""

    query = query.strip()

    # ----------------------------------------------------------------------
    # CASE 1: Empty Query (User just opened the filter or clicked a button)
    # ----------------------------------------------------------------------
    if not query:
        filter_dict = {}
        if file_type:
            filter_dict['file_type'] = file_type
        
        # Count total documents matching the filter
        total_results = await Media.count_documents(filter_dict)
        next_offset = offset + max_results

        if next_offset > total_results:
            next_offset = ''

        # For empty queries, we just show the most recent files
        cursor = Media.find(filter_dict)
        cursor.sort('$natural', -1)
        cursor.skip(offset).limit(max_results)
        files = await cursor.to_list(length=max_results)
        
        return files, next_offset, total_results

    # ----------------------------------------------------------------------
    # CASE 2: Text Search (The Fast Way)
    # ----------------------------------------------------------------------
    # This uses the Compound Index (file_name + caption) you created in Atlas.
    
    filter_dict = {'$text': {'$search': query}}

    if file_type:
        filter_dict['file_type'] = file_type

    try:
        total_results = await Media.count_documents(filter_dict)
        next_offset = offset + max_results

        if next_offset > total_results:
            next_offset = ''

        # We search and Project the "score" to sort by relevance
        cursor = Media.find(
            filter_dict,
            {"score": {"$meta": "textScore"}}
        )
        
        # Sort by relevance (best match first)
        cursor.sort([("score", {"$meta": "textScore"})])
        
        cursor.skip(offset).limit(max_results)
        files = await cursor.to_list(length=max_results)

    except Exception as e:
        logger.exception(f"Error in text search: {e}")
        return [], 0, 0

    return files, next_offset, total_results


async def get_file_details(query):
    filter = {'file_id': query}
    cursor = Media.find(filter)
    filedetails = await cursor.to_list(length=1)
    return filedetails


def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0

    for i in s + bytes([22]) + bytes([4]):
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0

            r += bytes([i])

    return base64.urlsafe_b64encode(r).decode().rstrip("=")


def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")


def unpack_new_file_id(new_file_id):
    """Return file_id, file_ref"""
    decoded = FileId.decode(new_file_id)
    file_id = encode_file_id(
        pack(
            "<iiqq",
            int(decoded.file_type),
            decoded.dc_id,
            decoded.media_id,
            decoded.access_hash
        )
    )
    file_ref = encode_file_ref(decoded.file_reference)
    return file_id, file_ref
