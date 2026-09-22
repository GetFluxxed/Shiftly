import json

from fastapi import Request


class RequestBodyError(ValueError):
    pass


async def bounded_json(request: Request, *, max_body: int, invalid_message: str):
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) <= 0 or int(content_length) > max_body:
                raise RequestBodyError("Request is empty or too large.")
        except ValueError as error:
            raise RequestBodyError(invalid_message) from error
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_body:
            raise RequestBodyError("Request is empty or too large.")
        chunks.append(chunk)
    if size <= 0:
        raise RequestBodyError("Request is empty or too large.")
    try:
        payload = json.loads(b"".join(chunks))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RequestBodyError(invalid_message) from error
    if not isinstance(payload, dict):
        raise RequestBodyError(invalid_message)
    return payload
