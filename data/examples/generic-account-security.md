# Generic example: account password reset

> TRAINING EXAMPLE ONLY — This is not verified Friskit documentation. It exists to demonstrate retrieval over more than one product-specific source.

## Purpose
A typical web application may allow a user to reset a forgotten password using a registered email address.

## Example workflow
1. Open the application's sign-in page.
2. Select the link labelled "Forgot password?" if the application provides one.
3. Enter the email address associated with the account.
4. Submit the request and check the inbox, spam, or junk folder for a reset message.
5. Open the reset link and choose a new password that meets the application's stated policy.
6. Return to sign in with the new password.

## Security considerations
- Do not reveal whether an email address has an account; use a neutral confirmation message.
- Reset tokens should be random, single-use, time-limited, and stored securely.
- Never ask users to send passwords or reset tokens to support staff.
- Revoke existing sessions after a successful reset when the product's security policy requires it.

## Troubleshooting
If the email does not arrive, verify the address, check spam, wait briefly, and request a new link. If a link has expired, request another one. The exact labels and rules depend on the application.
