# Making email really work

## Why "forgot password" seemed to do nothing
Out of the box RouteLync uses the **console email backend**: every email is *printed in the terminal window that runs the server*
and is never sent to an inbox. That is a development setting. The verification-code page and the "check your email" page now say so
while it is active. To send real email you must configure an SMTP account (below).

## Settings (all in `.env`; nothing is stored in the code)
| Variable | Meaning |
|---|---|
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` for real delivery |
| `EMAIL_HOST`, `EMAIL_PORT` | your provider's SMTP server, for example `smtp.gmail.com`, `587` |
| `EMAIL_USE_TLS` / `EMAIL_USE_SSL` | `True` for TLS on port 587, or SSL on port 465 (never both) |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | the SMTP login. For Gmail this must be an **app password** |
| `DEFAULT_FROM_EMAIL` | the sender shown to citizens. It must be an address authorized by your SMTP provider. |
| `DEFAULT_REPLY_TO_EMAIL` | the address used when a citizen presses Reply; defaults to a non-routable `no-reply@routelync.local`. |
| `EMAIL_TIMEOUT` | seconds to wait for the mail server (default 10) so a slow server cannot hang a page |
| `SITE_URL` | the public base URL used in password-reset and notification links; use a LAN address for same-Wi-Fi phone testing or HTTPS in production. |

### Gmail example
1. Turn on 2-step verification for the Google account.
2. Create an *app password* (Google Account, Security, App passwords) and copy the 16 characters.
3. If you do not want the authenticated Gmail address shown, set up and verify a sender alias in Gmail under **Settings → Accounts and Import → Send mail as**, or use a dedicated sender mailbox. Gmail may replace an unverified `From` address with the authenticated account.
4. Put the credentials and verified sender in `.env`:
```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-account@gmail.com
EMAIL_HOST_PASSWORD=the-app-password
DEFAULT_FROM_EMAIL=RouteLync <verified-sender@your-domain.com>
DEFAULT_REPLY_TO_EMAIL=no-reply@your-domain.com
```
Use the address verified with Gmail for `DEFAULT_FROM_EMAIL`; set `DEFAULT_REPLY_TO_EMAIL` to an address that does not route replies to your personal inbox. Restart the server after changing `.env`.
Other providers (Outlook/Office 365, Brevo, SendGrid, Amazon SES, your college mail server) use the same variables with their own host,
port and login. Gmail is fine for a demonstration; for real traffic use a transactional email service and a domain you own
(otherwise messages may land in spam).

## Open the development site on a phone
`127.0.0.1` and `localhost` refer to the phone itself, so links using either address cannot reach a server running on your PC.
For testing on the same Wi-Fi:

1. On the PC, run `ipconfig` and note the **IPv4 Address** under the active Wi-Fi adapter.
2. Set `SITE_URL=http://<PC-WI-FI-IP>:8000` in `.env`. Django adds the configured site host to `ALLOWED_HOSTS`.
3. Stop the current server and restart it so it listens on the network:
   `python manage.py runserver 0.0.0.0:8000`
4. Open `http://<PC-WI-FI-IP>:8000/` on the phone. If Windows Firewall prompts, allow access on private networks.
5. Request a **new** password-reset email; links already sent still contain the old host.

The PC and phone must be on the same Wi-Fi. This development server is not for public internet access; use a deployed HTTPS site
or a secure HTTPS tunnel for access from another network.

## Check it works (this uses the exact settings the website uses)
```bash
python manage.py send_test_email you@example.com
```
It prints the backend and server (never the password), then either "The mail server accepted the message" or the precise failure
(wrong password, blocked port, timeout). Then check the inbox **and the spam folder**.

## What the application does with email
- **Registration:** an account starts unverified. A 6-digit code is emailed; it works once, expires after 10 minutes, allows 5 wrong
  guesses, and a new code can be requested after 60 seconds (at most 5 per hour). Only a keyed hash of the code is stored.
- **Sign-in** is refused for an unverified citizen (who is sent to the verification page). Staff accounts made by an administrator
  and the demo accounts do not need verification.
- **Forgot password:** the answer is the same whether or not the address has an account. A time-limited, single-use link is emailed.
  After a successful reset a "your password was changed" email is sent (it never contains the password).
- **If sending fails** the page says so and offers "Send a new code"; it never claims an email was sent when it was not.
- Codes and reset links are never written to the logs. (The console backend prints whole emails to the terminal; use it only in development.)

## Production
`python manage.py check --deploy` warns (`routelync.W001` / `W002`) when the email backend is a development one or the SMTP settings are
incomplete. Reset links use HTTPS when the site is served over HTTPS; set `DJANGO_ALLOWED_HOSTS` to your real domain.
