Here's an explanation of the authentication and authorization process in logic.py:

**Core Concepts:**

1.  **JWT (JSON Web Tokens):** The system uses JWT for authentication. When a user logs in successfully, the server generates two tokens:
    *   **Access Token:** A short-lived token containing user information (payload) like ID, roles, permissions, and an expiration time. It's sent with every request to protected API endpoints.
    *   **Refresh Token:** A longer-lived, opaque token stored securely by the client and also tracked in the server's database (`Token` table). It's used to obtain a new access token when the current one expires, without requiring the user to log in again.
2.  **Flask `g` Object:** This is a request-bound global object. The decorators use `g.user` and `g.auth_payload` to store the authenticated user's database object and the validated token payload, making them easily accessible within the request context and subsequent decorators/route handlers.
3.  **Decorators:** Python decorators (`@login_required`, `@approved_required`, `@admin_only`, `@aup_require`) wrap Flask route functions to add authentication and authorization checks before the main route logic runs.

**Authentication Flow (Login):**

1.  A user sends credentials (e.g., username, password) to a login endpoint (like `/api/auth/login` or `/api/auth/login/lk` defined in `maps_backend/auth/routes.py`).
2.  The server verifies the credentials against the `Users` database table.
3.  If credentials are valid:
    *   The `get_access_token(user_id)` function is called:
        *   It fetches the user's details from the `Users` table.
        *   It builds a payload containing `user_id`, `name`, `login`, `roles` (list of dicts), `department_id`, `faculties`, `can_edit` permissions (based on role/AUP), `approved_lk` status, and an expiration timestamp (`exp`).
        *   It encodes this payload into a JWT access token using the application's `SECRET_KEY`.
    *   The `get_refresh_token(user_id, user_agent)` function is called:
        *   It generates a unique refresh token string.
        *   It removes any old refresh tokens for the same user and browser (`user_agent`) from the `Token` table.
        *   It saves the new refresh token, user ID, user agent, and its expiration time (`ttl`) into the `Token` table.
4.  The server sends both the `access` token and the `refresh` token back to the client.

**Authorization Flow (Accessing Protected Routes):**

1.  The client makes a request to a protected API endpoint, including the access token in the `Authorization` header (e.g., `Authorization: Bearer <your_access_token>`).
2.  The `@login_required` decorator (which must be applied first) intercepts the request:
    *   It extracts the token from the header.
    *   It calls `verify_jwt_token(token)` to decode and validate the token's signature and expiration using the `SECRET_KEY`.
    *   If the token is valid, it retrieves the corresponding user from the `Users` table using the `user_id` from the token payload.
    *   If the user exists, it stores the user object in `g.user` and the decoded token payload in `g.auth_payload`.
    *   If the token is invalid or the user doesn't exist, it returns a `401 Unauthorized` error.
3.  If `@login_required` succeeds, subsequent decorators run:
    *   `@approved_required`: Checks if `g.auth_payload['approved_lk']` is true. Returns `403 Forbidden` if not.
    *   `@admin_only`: Checks if the list `g.auth_payload['roles']` contains a role with `id == 1`. Returns `403 Forbidden` if not.
    *   `@aup_require`:
        *   Requires an `Aup` header in the request (returns `400 Bad Request` if missing).
        *   Validates the AUP exists in `AupInfo` (returns `404 Not Found` if not).
        *   Checks if the user's role (from `g.auth_payload['roles']`) and associated faculty/department (from `g.auth_payload`) permit access to the requested AUP. Returns `403 Forbidden` if not allowed. Admins (role ID 1) generally bypass the faculty/department check.
4.  If all decorators pass, the original route handler function is executed.

**Token Refresh Flow:**

1.  If the client makes a request with an expired access token, the `verify_jwt_token` function within `@login_required` will fail, resulting in a `401 Unauthorized` response.
2.  The client should detect this 401 error and send a request to the refresh endpoint (`/api/auth/refresh` in `maps_backend/auth/routes.py`), providing both the (expired) access token and the refresh token.
3.  The refresh endpoint handler (`refresh_view`):
    *   Calls `verify_jwt_token` on the provided access token. *Note: As currently implemented, this checks expiry, which might prevent refresh if the token is truly expired. Typically, only the signature might be verified here, or the payload decoded ignoring expiry, just to get the `user_id`.*
    *   Calls `verify_refresh_token(refresh_token)` to check if the refresh token exists in the `Token` table and hasn't expired (`ttl`).
    *   If *both* tokens are considered valid by these checks, it generates *new* access and refresh tokens using `get_access_token` and `get_refresh_token` for the `user_id` from the access token payload.
    *   It returns the new tokens to the client.
    *   If either token verification fails, it returns a `401 Unauthorized` error, forcing the user to log in again.