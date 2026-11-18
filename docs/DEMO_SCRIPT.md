# RouteLync demonstration script

## Before the demo (once, about 30 seconds)
```bash
python manage.py migrate
python manage.py setup_demo --password "choose-a-password"
python manage.py runserver
```
`setup_demo` loads departments, areas and wards, demo accounts, the training data, trains and activates a model, and
submits 13 sample complaints through the real pipeline (so routing, priorities, SLA deadlines and the duplicate flag are
genuine output). It deliberately does **not** create the scenario complaint below; you submit that one live.

| Role | Sign in with |
|---|---|
| Citizen | `citizen@routelync.test` |
| Electricity officer | `officer.electricity@routelync.test` |
| Electricity head | `head.electricity@routelync.test` |
| Field worker (Electricity) | `worker.ravi.kumar@routelync.test` |
| Water officer | `officer.water@routelync.test` |
| Other officers (17 departments) | `officer.parks@`, `officer.health@`, `officer.town@`, `officer.property@`, `officer.trade@`, `officer.fire@`, `officer.animal@`, `officer.education@`, `officer.social@`, `officer.civil@`, `officer.traffic@`, `officer.environment@`, `officer.advertisements@` (all `...@routelync.test`) |
| Administrator | `admin@routelync.test` |

Use two browsers (or one normal and one private window) so two people can be signed in at once.

> After `python manage.py setup_staff_accounts ...` the staff logins below are renamed to the department format
> (`electricityofficer1@company.com`, `electricityworker1@company.com`, ...). See `docs/STAFF_ACCOUNTS.md`.

## The 13-step scenario
1. **Citizen signs in** (`citizen@routelync.test`). They land on *My complaints*. (Optional: register a new account first. In development mode the 6-digit code is printed in the terminal running the server; with SMTP configured it arrives by email.)
2. **Submit the complaint.** *Report a problem*, then enter: Area **Jayanagar**, Ward **154**, Street **4th Main Road**,
   Landmark **Near Metro**, Description: *The streetlight near the junction has not been working for three days and the
   road is very dark at night.* Title: *Streetlight not working near junction*. Point out that the description is compulsory (at least 5 words, with a live counter, and it must really describe a problem: try `tttttttttrttttt nsomtehing`, which is refused and appears under *Not submitted* on the citizen's page with an *Edit and submit again* button): the classifier reads text only, and the photo is optional support. Try submitting with only a photo to show it is refused.
3. **Choose the location and add the photo.** Type `Bengaluru Majestic Bus Stand` in the search box and pick a result (or tap the map, drag the pin, or press *Use my current location*); the address fills in. The photo is **compulsory** (JPG/PNG/WEBP).
   Point out: GPS is optional, the file type is checked by content, and the photo's hidden camera data is removed.
4. **Submit.** The page shows the complaint with the citizen's plain-language progress tracker (no internal details).
5. **Show what the system decided.** Sign in as the Electricity officer, open the complaint: predicted department,
   **the model's actual confidence** (read it from the screen; it was about 98% in the test run), model version,
   probabilities for all four departments, and the influential terms (*streetlight*, *not*, *working* ...). Then, as the
   administrator, open **AI model > Try the model** and paste the description to show every processing stage:
   cleaning, tokens, stop-words removed, stemming, TF-IDF terms, Naive Bayes probabilities.
6. **It is already in the Electricity queue** (*Complaints* tab). The Water officer's queue does not contain it.
7. **Filter like an officer:** Area Jayanagar, Ward 154, Street 4th Main Road. Also show *By location* (Area > Ward >
   Street drill-down) and the *Map* tab (the new marker appears).
8. **Assign** the complaint to **Ravi Kumar** (the picker lists only available Electricity workers).
9. **Field worker** (`worker.ravi.kumar@...`) sees only assigned jobs, opens it and presses *Start work*.
10. **Complete the job:** describe the work and attach the photo of the finished fix (**required**; the form and the server both refuse without it), then *Submit for verification*. The citizen still sees "Work in progress" because the officer has not verified it yet, and cannot see the photo yet.
11. **Officer verifies:** the complaint shows *needs your verification*; press *Approve*.
12. **Citizen sees "Resolved"**: the **photo of the completed work appears inside the Progress card with the status steps** (visual proof), plus the worker's description and a notification under the bell. Show that the officer could not have marked it Resolved without that photo.
13. **Citizen confirms** it is fixed (the complaint closes) and **gives feedback** (rating and comment).

## Extra segments (pick what time allows)
- **Human in the loop.** Administrator > *Verification queue* holds RL-000013 (a nonsense complaint the model could not
  place). Choose a department; show the "use as verified training example" option and the correction recorded.
- **Duplicate detection.** Open RL-000002 as the Roads officer: it is flagged as a possible duplicate of RL-000001
  (about 73% similar). Show that a person must decide and nothing merges automatically.
- **Administrator dashboard.** Counts, charts by department/area/ward, resolution time, feedback, AI metrics and the
  confusion matrix. Then *AI model > Train a new model*: it is not active until you press Activate.
- **Audit log.** Every status change, correction, training run, sign-in and failed sign-in, with who and when.
- **SLA and escalation.** `python manage.py check_sla` warns officers near the deadline and escalates overdue
  complaints to the Department Head, then the Administrators. (To demonstrate quickly, shorten a priority's hours on the
  *Departments > SLA settings* page, submit a complaint, and run the command.)
- **Security.** As the citizen, open `/officer/` (access denied page). As the Water officer, try the Electricity
  complaint's address (not found). Show the lockout after five wrong passwords.

## If something goes wrong
- *"No active ML model"*: run `python manage.py train_complaint_model --activate`.
- *Map is grey*: the tiles need an internet connection; the markers still work.
- *Geolocation button does nothing*: browsers only allow it on `localhost` or HTTPS.
