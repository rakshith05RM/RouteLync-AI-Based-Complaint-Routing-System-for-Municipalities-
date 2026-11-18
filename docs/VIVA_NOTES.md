# Viva preparation: answers tied to this implementation

## Django
- **What is Django and why use it?** A Python web framework with ORM, authentication, sessions, CSRF protection, form validation and an admin site built in. It let the project spend its effort on routing, workflow and security rules instead of re-building basics.
- **What is the ORM and why use it?** It maps tables to Python classes (`Complaint`, `Department` ...). Queries are built as objects, values are sent as parameters, so SQL injection is prevented, and the same code ran on SQLite and MySQL 8.
- **How does authentication work?** `authenticate()` checks the email and the PBKDF2-hashed password; login stores the user id in a server-side session and the browser keeps only an HttpOnly session cookie. Login is by email (custom `User` model). Five failures lock that email and network for 15 minutes.
- **How does authorization work?** After login the role (citizen, officer, worker, admin) decides the landing page. Every view is protected on the server by `RoleRequiredMixin`; officers and workers additionally by `DepartmentScopedMixin`; and all complaint queries start from `complaints_visible_to(user)`. Hiding a button is never the only protection. A test lists every URL and fails if a route has no access decision.
- **Why a custom user model?** One login identity for all roles, and it must exist before the first migration.

## Database
- **Tables and relationships?** 23 tables (`docs/er_diagram.mmd`). A user has at most one profile (citizen, officer or worker). A complaint has one location, many images, history rows, assignments, remarks, resolutions, escalation events and duplicate flags, and at most one feedback.
- **Why not one big table?** Normalisation: location, images and history change independently. The area is derived from the ward, so it is stored once (third normal form).
- **Foreign keys, constraints, indexes?** `PROTECT` stops deleting a department that has staff or complaints. Check constraints enforce latitude (-90 to 90), longitude (-180 to 180), ratings 1 to 5, confidence 0 to 1, positive SLA hours. A unique (area, number) pair identifies a ward. Indexes cover (department, status), (status, SLA deadline) and (ward, street) because dashboards filter on them.
- **Why is "one active assignment" a nullable unique column?** MySQL has no conditional unique index. The column holds the complaint id while active and NULL afterwards; unique indexes allow many NULLs.
- **Transactions?** Submission, routing, each workflow action and each status change run in `transaction.atomic()`, with the complaint row locked (`select_for_update`). A test forces a failure mid-way and shows nothing is left behind.

## NLP
- **Tokenization:** splitting text into words (NLTK `RegexpTokenizer`).
- **Stop-word removal:** removing very common words. The custom list **keeps** "no", "not", "without", "off", "out", because "no water" and "not working" depend on them.
- **Other steps:** lower-casing, removing digits and punctuation, expanding contractions, normalising "street light / street-lamp" to one word, stemming (Snowball).
- **TF-IDF:** a word's weight is its (damped) frequency in the complaint times how rare it is across complaints; common words count less. It turns text into numbers.

## Machine learning
- **Why Multinomial Naive Bayes?** It is fast, works well on sparse word counts and small datasets, gives class probabilities (needed for the confidence threshold) and is easy to explain.
- **How it decides:** pick the department with the highest P(department) times the product of P(word | department), assuming words are independent given the department.
- **Prior / conditional probability:** the prior is how common each department is in training (equal here); the conditional is how often a word appears in that department's complaints.
- **Laplace smoothing (alpha):** adds a small count to every word so an unseen word never makes a probability zero. Grid search chose alpha = 0.03.
- **Train/test:** stratified 80/20 split; tuning (cross-validation) used only the 960 training rows; the 240 test rows were used once. A test checks the two sets share no text.
- **Metrics:** accuracy = correct/all. Precision = of complaints predicted Electricity, how many truly were. Recall = of true Electricity complaints, how many were found. F1 = their harmonic mean. The confusion matrix shows which departments get mixed up.
- **Honest numbers** (`docs/ml_results.md`): test split 1.000 (optimistic: generated sentences share building blocks); hand-written challenge set 0.828 (normal 0.80, hard 0.93). The challenge set is the realistic figure. Data is synthetic and says so.
- **Why a confidence threshold?** Below it the complaint goes to a person. It is chosen from out-of-fold predictions, never below 0.50, stored per model and editable by an administrator.
- **Limits:** Naive Bayes can be confidently wrong (a vague complaint with the word "noise" was routed to Electricity with 0.92). That is why administrators can correct routing and why corrections feed future training.
- **Explainability:** influential terms are words that pushed the model toward its answer compared with the runner-up; they are not a causal proof.

## System
- **How is a complaint routed?** Saved first, then `predict()`; if confidence >= threshold and the department is active it goes to that department's queue, otherwise to the administrator's verification queue. If the model is missing or crashes it also goes to verification, so a complaint is never lost.
- **Department and location filtering:** the officer's queryset is limited to their department in the database query before any filter runs; area/ward/street are joins on the complaint's ward.
- **SLA:** deadline = submission time + hours for the priority (editable, example values 4/12/24/72). Priority comes from 14 transparent keyword rules, not ML.
- **Escalation:** `check_sla` warns near the deadline, escalates overdue complaints to the Department Head, then to Administrators. It records events and a level and never overwrites the status.
- **Incorrect AI prediction:** an administrator moves the complaint; the correction is stored with the model's original guess and can become a verified training example. Training is never automatic.
- **Security:** hashed passwords, CSRF tokens, HttpOnly sessions, server-side authorization, validated and re-encoded images, rate limits, Content-Security-Policy, audit log, secrets only in environment variables, `check --deploy` clean.
- **Privacy:** see `docs/SECURITY.md` (who can see what).

## Two design decisions to be ready to defend
- **Why is the description compulsory (minimum 8 words) and the photo optional?** The classifier is a text model (TF-IDF + Naive Bayes); it cannot read images. A complaint with only a photo would have nothing to classify, so the text is required and the photo only supports it. The minimum is a setting; filler such as "test test test" does not count.
- **Why can a complaint not be Resolved without a photo?** It gives the citizen visual proof instead of a status label that merely changed. The rule lives in the single status-change function (`transition_complaint`), so no screen or script can bypass it. The photo is stored on the complaint as `resolution_photo`, separate from the citizen's own photo, and is shown to the citizen only after an officer has verified the work. Reopening clears it, so a new proof is needed next time.

## Email verification, description check and location (added later)
- **How do you stop fake accounts?** The account is pending until the person enters the 6-digit code that was emailed to the address; login is refused until then.
- **Why store only a hash of the code?** A leaked database should not reveal live codes. The hash is keyed (HMAC with the secret key), the code expires in 10 minutes, works once and allows 5 guesses.
- **Why the same page when the email is already registered?** So the form cannot be used to find out who has an account; the real owner is told by email instead.
- **How do you decide a description is a real municipal issue?** Rules, not AI: format checks (gibberish, filler, repeated words, links, spam), then a visible vocabulary of strong terms ("pothole", "garbage") and weak terms ("water", "road") that count only with a problem word ("broken", "no"). Out-of-scope matters (tax, certificates) get the "unsupported" message; local-language text is accepted and sent to a person. The classifier's confidence is never used as proof that text is valid.
- **How accurate is that check?** On small hand-written sets: before widening the vocabulary it wrongly rejected 10% (3 of 30) of fresh valid complaints and 28% (18 of 64) of the independent challenge set; after widening, 5% (1 of 20) of a second fresh set, with no junk accepted. The final tuned sets now show no errors, which proves the rules still work, not that they generalise. Treat all of it as indicative.
- **Why is a rejected submission not stored as a complaint?** It would pollute statistics and routing. It is a draft (no reference number, never routed) so the citizen can fix and resubmit.
- **How do you keep the address and the pin consistent?** The server signs each search result and each reverse lookup (address, place id, coordinates, user, time). The form must submit coordinates matching that token, or it is refused.
- **Which map/geocoding service?** OpenStreetMap-based (Photon or Nominatim), called from the server. The public servers are fair-use only; production needs your own or a commercial server.

## Seventeen departments
- **How many departments does the AI handle and why?** Seventeen: a municipality has far more than four. The label set is just the list of departments, so adding one means adding its example complaints and retraining; no code or screen changes.
- **Does accuracy drop with more classes?** Yes: the original 64 hand-written complaints went from 82.8% to 78.1% when 13 departments were added, because neighbouring departments are confusable. Overall, 85.1% on 194 hand-written complaints and 94.1% on 51 fresh ones (after adding everyday-speech training phrases). Low-confidence complaints go to a person.
- **Why did complaints for the new departments get refused at first?** The description check's vocabulary only knew four departments. It now covers all 17, with the trained model as a second opinion for unusual wording.

## Questions to expect, with the honest answer
- *"Is the 100% accuracy real?"* It is real on that split but not meaningful; the hand-written challenge set (82.8%) is the fair figure, and neither uses real municipal data.
- *"Did you test on MySQL?"* Yes: the full suite and the demo setup were run against MySQL 8.0 (see `docs/TESTING.md`).
- *"What is not built?"* Email/SMS delivery, image-based AI, multilingual routing, a background job runner. They are listed as Future Enhancements.
