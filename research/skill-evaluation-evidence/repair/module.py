def can_read(user, record):
    return user["id"] == record["owner"] and user.get("authenticated", False)

def title(record):
    return record["title"]
