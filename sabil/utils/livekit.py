from livekit import api

API_KEY = "devkey"
API_SECRET = "secret123"

def create_token(identity, room, name=None):
    token = api.AccessToken(API_KEY, API_SECRET)

    token.with_identity(identity)
    token.with_name(name or identity)

    token.with_grants(
        api.VideoGrants(
            room_join=True,
            room=room,
            can_publish=True,
            can_subscribe=True,
        )
    )
    print(f"🔑 Generated token: {token.to_jwt()[:50]}...")  # Debug
    return token.to_jwt()