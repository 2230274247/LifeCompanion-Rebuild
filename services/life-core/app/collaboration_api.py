from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from .auth import verified_claims_from_request
from .collaboration import (
    AgentQuery,
    AvailabilityCreate,
    CareForwardCreate,
    ContributionCreate,
    FriendRequestCreate,
    GrantCreate,
    GrantRequestCreate,
    MessageCreate,
    MessageUpdate,
    NotificationUpdate,
    ProfileUpdate,
    ReactionCreate,
    SharedMemoryInviteCreate,
    SharedMemoryJoinInviteCreate,
    SharedStatusCreate,
    SpaceCreate,
    SpaceInviteCreate,
    SpaceOwnerUpdate,
)


collaboration_router = APIRouter()


def current_collab_identity(request: Request) -> tuple[str, str, dict[str, Any]]:
    claims = verified_claims_from_request(request)
    librechat_user_id = claims["id"]
    profile = request.app.state.collaboration.ensure_profile(librechat_user_id, claims)
    return profile["user_id"], librechat_user_id, profile


@collaboration_router.get("/api/v1/collaboration/me")
def collaboration_me(identity=Depends(current_collab_identity)):
    _user_id, _librechat_id, profile = identity
    return {"profile": profile}


@collaboration_router.patch("/api/v1/collaboration/me")
def update_collaboration_profile(
    body: ProfileUpdate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {"profile": request.app.state.collaboration.update_profile(identity[0], body)}


@collaboration_router.get("/api/v1/users/search")
def search_collaboration_users(
    q: str = Query(min_length=1, max_length=80),
    request: Request = None,
    identity=Depends(current_collab_identity),
):
    return {"users": request.app.state.collaboration.search_profiles(identity[0], q)}


@collaboration_router.get("/api/v1/friends")
def list_collaboration_friends(request: Request, identity=Depends(current_collab_identity)):
    return request.app.state.collaboration.list_friends(identity[0])


@collaboration_router.post("/api/v1/friends/requests")
def create_collaboration_friend_request(
    body: FriendRequestCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {"request": request.app.state.collaboration.send_friend_request(identity[0], body)}


@collaboration_router.post("/api/v1/friends/requests/{request_id}/accept")
def accept_collaboration_friend_request(
    request_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "request": request.app.state.collaboration.friend_request_action(
            identity[0], request_id, "accept"
        )
    }


@collaboration_router.post("/api/v1/friends/requests/{request_id}/reject")
def reject_collaboration_friend_request(
    request_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "request": request.app.state.collaboration.friend_request_action(
            identity[0], request_id, "reject"
        )
    }


@collaboration_router.post("/api/v1/friends/requests/{request_id}/cancel")
def cancel_collaboration_friend_request(
    request_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "request": request.app.state.collaboration.friend_request_action(
            identity[0], request_id, "cancel"
        )
    }


@collaboration_router.delete("/api/v1/friends/{other_user_id}")
def unfriend_collaboration_user(
    other_user_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    request.app.state.collaboration.unfriend(identity[0], other_user_id)
    return {"status": "removed"}


@collaboration_router.post("/api/v1/blocks/{other_user_id}")
def block_collaboration_user(
    other_user_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    request.app.state.collaboration.block_user(identity[0], other_user_id)
    return {"status": "blocked"}


@collaboration_router.delete("/api/v1/blocks/{other_user_id}")
def unblock_collaboration_user(
    other_user_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    request.app.state.collaboration.unblock_user(identity[0], other_user_id)
    return {"status": "unblocked"}


@collaboration_router.get("/api/v1/spaces")
def list_collaboration_spaces(request: Request, identity=Depends(current_collab_identity)):
    return {"spaces": request.app.state.collaboration.list_spaces(identity[0])}


@collaboration_router.post("/api/v1/spaces")
def create_collaboration_space(
    body: SpaceCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {"space": request.app.state.collaboration.create_space(identity[0], body)}


@collaboration_router.get("/api/v1/spaces/{space_id}")
def collaboration_space_detail(
    space_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {"space": request.app.state.collaboration.space_detail(identity[0], space_id)}


@collaboration_router.post("/api/v1/spaces/{space_id}/invites")
def invite_to_collaboration_space(
    space_id: str,
    body: SpaceInviteCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "invite": request.app.state.collaboration.invite_to_space(identity[0], space_id, body)
    }


@collaboration_router.post("/api/v1/space-invites/{invite_id}/accept")
def accept_collaboration_space_invite(
    invite_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "invite": request.app.state.collaboration.space_invite_action(
            identity[0], invite_id, "accept"
        )
    }


@collaboration_router.post("/api/v1/space-invites/{invite_id}/reject")
def reject_collaboration_space_invite(
    invite_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "invite": request.app.state.collaboration.space_invite_action(
            identity[0], invite_id, "reject"
        )
    }


@collaboration_router.post("/api/v1/space-invites/{invite_id}/cancel")
def cancel_collaboration_space_invite(
    invite_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "invite": request.app.state.collaboration.space_invite_action(
            identity[0], invite_id, "cancel"
        )
    }


@collaboration_router.patch("/api/v1/spaces/{space_id}/owner")
def transfer_collaboration_space_owner(
    space_id: str,
    body: SpaceOwnerUpdate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "space": request.app.state.collaboration.transfer_owner(identity[0], space_id, body)
    }


@collaboration_router.post("/api/v1/spaces/{space_id}/leave")
def leave_collaboration_space(
    space_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    request.app.state.collaboration.leave_space(identity[0], space_id)
    return {"status": "left"}


@collaboration_router.delete("/api/v1/spaces/{space_id}")
def archive_collaboration_space(
    space_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    request.app.state.collaboration.archive_space(identity[0], space_id)
    return {"status": "archived"}


@collaboration_router.get("/api/v1/spaces/{space_id}/messages")
def list_collaboration_space_messages(
    space_id: str,
    request: Request,
    after: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=80, ge=1, le=200),
    identity=Depends(current_collab_identity),
):
    return {
        "messages": request.app.state.collaboration.list_space_messages(
            identity[0], space_id, after, limit
        )
    }


@collaboration_router.post("/api/v1/spaces/{space_id}/messages")
def create_collaboration_space_message(
    space_id: str,
    body: MessageCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "message": request.app.state.collaboration.send_space_message(
            identity[0], space_id, body
        )
    }


@collaboration_router.patch("/api/v1/spaces/{space_id}/messages/{message_id}")
def update_collaboration_space_message(
    space_id: str,
    message_id: str,
    body: MessageUpdate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "message": request.app.state.collaboration.update_message(
            identity[0], space_id, message_id, body
        )
    }


@collaboration_router.delete("/api/v1/spaces/{space_id}/messages/{message_id}")
def delete_collaboration_space_message(
    space_id: str,
    message_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    request.app.state.collaboration.delete_message(identity[0], space_id, message_id)
    return {"status": "deleted"}


@collaboration_router.post("/api/v1/spaces/{space_id}/messages/{message_id}/reactions")
def react_to_collaboration_space_message(
    space_id: str,
    message_id: str,
    body: ReactionCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return request.app.state.collaboration.react_message(
        identity[0], space_id, message_id, body
    )


@collaboration_router.get("/api/v1/direct-messages/{peer_user_id}")
def list_collaboration_direct_messages(
    peer_user_id: str,
    request: Request,
    after: str | None = Query(default=None, max_length=40),
    identity=Depends(current_collab_identity),
):
    return {
        "messages": request.app.state.collaboration.direct_messages(
            identity[0], peer_user_id, after
        )
    }


@collaboration_router.post("/api/v1/direct-messages/{peer_user_id}")
def send_collaboration_direct_message(
    peer_user_id: str,
    body: MessageCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "message": request.app.state.collaboration.send_direct_message(
            identity[0], peer_user_id, body
        )
    }


@collaboration_router.get("/api/v1/collaboration/events")
def wait_collaboration_events(
    scope_key: str = Query(min_length=3, max_length=120),
    after_id: int = Query(default=0, ge=0),
    wait_seconds: int = Query(default=20, ge=0, le=20),
    request: Request = None,
    identity=Depends(current_collab_identity),
):
    return {
        "events": request.app.state.collaboration.wait_events(
            identity[0], scope_key, after_id, wait_seconds
        )
    }


@collaboration_router.get("/api/v1/grants")
def list_collaboration_grants(request: Request, identity=Depends(current_collab_identity)):
    return {"grants": request.app.state.collaboration.list_grants(identity[0])}


@collaboration_router.post("/api/v1/grants")
def create_collaboration_grant(
    body: GrantCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {"grant": request.app.state.collaboration.create_grant(identity[0], body)}


@collaboration_router.delete("/api/v1/grants/{grant_id}")
def revoke_collaboration_grant(
    grant_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    request.app.state.collaboration.revoke_grant(identity[0], grant_id)
    return {"status": "revoked"}


@collaboration_router.get("/api/v1/grants/requests")
def list_collaboration_grant_requests(
    request: Request, identity=Depends(current_collab_identity)
):
    return request.app.state.collaboration.list_grant_requests(identity[0])


@collaboration_router.post("/api/v1/grants/requests")
def create_collaboration_grant_request(
    body: GrantRequestCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {"request": request.app.state.collaboration.request_grant(identity[0], body)}


@collaboration_router.post("/api/v1/grants/requests/{request_id}/reject")
def reject_collaboration_grant_request(
    request_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "request": request.app.state.collaboration.decide_grant_request(
            identity[0], request_id, "reject"
        )
    }


@collaboration_router.post("/api/v1/grants/requests/{request_id}/cancel")
def cancel_collaboration_grant_request(
    request_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "request": request.app.state.collaboration.decide_grant_request(
            identity[0], request_id, "cancel"
        )
    }


@collaboration_router.get("/api/v1/availability")
def list_collaboration_availability(
    request: Request, identity=Depends(current_collab_identity)
):
    return {"availability": request.app.state.collaboration.list_availability(identity[0])}


@collaboration_router.post("/api/v1/availability")
def create_collaboration_availability(
    body: AvailabilityCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "availability": request.app.state.collaboration.create_availability(identity[0], body)
    }


@collaboration_router.delete("/api/v1/availability/{window_id}")
def revoke_collaboration_availability(
    window_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    request.app.state.collaboration.revoke_availability(identity[0], window_id)
    return {"status": "revoked"}


@collaboration_router.get("/api/v1/shared-availability/{owner_user_id}")
def read_shared_availability(
    owner_user_id: str,
    request: Request,
    start: str | None = Query(default=None, max_length=40),
    end: str | None = Query(default=None, max_length=40),
    identity=Depends(current_collab_identity),
):
    return {
        "availability": request.app.state.collaboration.shared_availability(
            identity[0], owner_user_id, start, end
        )
    }


@collaboration_router.get("/api/v1/shared-status/{owner_user_id}")
def read_shared_status(
    owner_user_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "statuses": request.app.state.collaboration.shared_status(identity[0], owner_user_id)
    }


@collaboration_router.post("/api/v1/shared-status")
def create_shared_status(
    body: SharedStatusCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {"status": request.app.state.collaboration.create_status(identity[0], body)}


@collaboration_router.get("/api/v1/shared-memories")
def list_collaboration_shared_memories(
    request: Request, identity=Depends(current_collab_identity)
):
    return {
        "shared_memories": request.app.state.collaboration.list_shared_memories(identity[0])
    }


@collaboration_router.post("/api/v1/shared-memories/invites")
def create_collaboration_shared_memory_invite(
    body: SharedMemoryInviteCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "invite": request.app.state.collaboration.create_shared_memory_invite(
            identity[0], body
        )
    }


@collaboration_router.post("/api/v1/shared-memories/invites/{invite_id}/accept")
def accept_collaboration_shared_memory_invite(
    invite_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return request.app.state.collaboration.shared_memory_invite_action(
        identity[0], invite_id, "accept"
    )


@collaboration_router.post("/api/v1/shared-memories/invites/{invite_id}/reject")
def reject_collaboration_shared_memory_invite(
    invite_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return request.app.state.collaboration.shared_memory_invite_action(
        identity[0], invite_id, "reject"
    )


@collaboration_router.post("/api/v1/shared-memories/invites/{invite_id}/cancel")
def cancel_collaboration_shared_memory_invite(
    invite_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return request.app.state.collaboration.shared_memory_invite_action(
        identity[0], invite_id, "cancel"
    )


@collaboration_router.post("/api/v1/shared-memory-joins/{invite_id}/accept")
def accept_collaboration_shared_memory_join(
    invite_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "invite": request.app.state.collaboration.shared_join_action(
            identity[0], invite_id, "accept"
        )
    }


@collaboration_router.post("/api/v1/shared-memory-joins/{invite_id}/reject")
def reject_collaboration_shared_memory_join(
    invite_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "invite": request.app.state.collaboration.shared_join_action(
            identity[0], invite_id, "reject"
        )
    }


@collaboration_router.get("/api/v1/shared-memories/{shared_id}")
def collaboration_shared_memory_detail(
    shared_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return request.app.state.collaboration.shared_memory_detail(identity[0], shared_id)


@collaboration_router.post("/api/v1/shared-memories/{shared_id}/contributions")
def create_collaboration_shared_memory_contribution(
    shared_id: str,
    body: ContributionCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "contribution": request.app.state.collaboration.add_contribution(
            identity[0], shared_id, body
        )
    }


@collaboration_router.post("/api/v1/shared-memories/{shared_id}/messages")
def create_collaboration_shared_memory_message(
    shared_id: str,
    body: MessageCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "message": request.app.state.collaboration.add_shared_message(
            identity[0], shared_id, body
        )
    }


@collaboration_router.post(
    "/api/v1/shared-memories/{shared_id}/messages/{message_id}/reactions"
)
def react_to_collaboration_shared_memory_message(
    shared_id: str,
    message_id: str,
    body: ReactionCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return request.app.state.collaboration.react_shared_message(
        identity[0], shared_id, message_id, body
    )


@collaboration_router.post("/api/v1/shared-memories/{shared_id}/invites")
def invite_to_collaboration_shared_memory(
    shared_id: str,
    body: SharedMemoryJoinInviteCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "invite": request.app.state.collaboration.invite_to_shared_memory(
            identity[0], shared_id, body
        )
    }


@collaboration_router.post("/api/v1/shared-memories/{shared_id}/leave")
def leave_collaboration_shared_memory(
    shared_id: str,
    request: Request,
    identity=Depends(current_collab_identity),
):
    request.app.state.collaboration.leave_shared_memory(identity[0], shared_id)
    return {"status": "left"}


@collaboration_router.post("/api/v1/spaces/{space_id}/agent/query")
def collaboration_space_agent_query(
    space_id: str,
    body: AgentQuery,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return request.app.state.collaboration.space_agent_query(identity[0], space_id, body)


@collaboration_router.post("/api/v1/shared-memories/{shared_id}/agent/query")
def collaboration_shared_memory_agent_query(
    shared_id: str,
    body: AgentQuery,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return request.app.state.collaboration.shared_memory_agent_query(
        identity[0], shared_id, body
    )


@collaboration_router.get("/api/v1/notifications")
def list_collaboration_notifications(
    request: Request, identity=Depends(current_collab_identity)
):
    return {
        "notifications": request.app.state.collaboration.list_notifications(identity[0])
    }


@collaboration_router.patch("/api/v1/notifications/{notification_id}")
def update_collaboration_notification(
    notification_id: str,
    body: NotificationUpdate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return {
        "notification": request.app.state.collaboration.update_notification(
            identity[0], notification_id, body
        )
    }


@collaboration_router.post("/api/v1/care/forward-requests")
def forward_collaboration_care(
    body: CareForwardCreate,
    request: Request,
    identity=Depends(current_collab_identity),
):
    return request.app.state.collaboration.forward_care(identity[0], body)
