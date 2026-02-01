import uuid


def get_uuid():
    return str(uuid.uuid4())


def get_uuid_int(uuid1):
    return uuid.UUID(uuid1).int
