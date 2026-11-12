from fastapi import Request, HTTPException


async def get_current_user(request: Request):

    user_id = getattr(request.state, "user_id", None)

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )

    return {
        "user_id": user_id,
        "user_code": request.state.user_code,
        "userrole": request.state.user_role,
        "session_id": request.state.session_id
    }