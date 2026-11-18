# Manual tests that need the real world

The automated tests use a test email backend and stand-in geocoder responses. They cannot prove real inbox delivery or the real
geocoding service. Do these once, on your machine, with the internet connected.

## A. Real email (after configuring SMTP, see EMAIL_SETUP.md)
1. `python manage.py send_test_email your-own-address@example.com`: expect "accepted", then the email in the inbox (check spam).
2. Register a new citizen with an address you can read. Expect the verification email with a 6-digit code; the page must NOT sign you in yet.
3. Enter a wrong code: "That code is not valid or has expired". Enter the right one: you are signed in.
4. Register again with the same address: you must see the same "if this address can be used" page, and the owner receives an
   "already have an account" email (no code).
5. Press "Send a new code" twice quickly: the second press says to wait. Wait 10 minutes: the old code no longer works.
6. Try to sign in with an unverified account: you are taken to the verification page.
7. Forgot password with the registered address: expect the reset email; use the link; set a new password; expect a "password changed"
   email without the password in it; the old password no longer works; the same link cannot be used twice.
8. Forgot password with an address that has no account: the same on-screen message, and no email is sent.
9. Switch the network off (or put a wrong SMTP password) and repeat 2 and 7: the page must say the email could not be sent, never "sent".

## B. Real location search (needs internet)
1. Open "Report a problem". Type `Bangalore` or `Bengaluru`: a dropdown of real places appears after a short pause.
2. Type `Bengaluru Majestic Bus Stand`: choose a result with the mouse, then with the arrow keys and Enter: the map moves, the pin appears,
   and address and street fill in. The text under the map shows the same coordinates.
3. Drag the pin a little, or tap elsewhere on the map: the coordinates and address change together.
4. On a device with location services, press "Use my current location" and allow the prompt: the pin goes to your position and the address fills in. On Windows, enable browser site access and Windows Location services; the page must be HTTPS or localhost. Deny the prompt: a clear message.
5. Choose a place outside the service area (for example search `Chennai` and tap the map far away): it is refused with the area message.
6. Turn off the network and type in the search box: "Location search is unavailable ... you can still tap the map".
7. Submit without choosing a location: blocked with a message. Submit with everything filled: the complaint page shows the address.
8. On a phone (use the PC's address on the same Wi-Fi; geolocation needs HTTPS or localhost, so for the GPS button use an HTTPS tunnel):
   type, tap a result, drag the pin with a finger, scroll the page.

## C. Automated browser test of the page logic (stand-in geocoder)
`cd e2e && npm install && ./run_location_e2e.sh` (see e2e/README.md).
