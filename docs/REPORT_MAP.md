# Mapping the project to the report

Use this to write each chapter from evidence that exists in the project. Do not claim anything that is not listed here.

## The 33 required sections
| # | Section | Write it from |
|---|---|---|
| 1-2 | Abstract, Introduction | your synopsis (section 1) plus: the implemented system extends the approved synopsis (see "Differences from the synopsis" below) |
| 3-5 | Problem, existing system, limitations | synopsis sections 2 and 3 |
| 6-8 | Proposed system, objectives, scope | synopsis; scope as built: 4 departments, synthetic training data, single city layout |
| 9 | Literature survey | only sources you have actually read; the synopsis lists real ones (below) |
| 10 | System requirements | `README.md` (Python 3.10+, MySQL 8, `requirements.txt`) |
| 11-12 | Functional / non-functional requirements | tables below |
| 13 | Architecture | `docs/DIAGRAMS.md` (data flow), README "Project layout": thin views, service layer, ML engine, MySQL |
| 14-18 | Use case, DFD, ER, class, sequence | `docs/DIAGRAMS.md`, `docs/er_diagram.mmd`, `docs/lifecycle.mmd` |
| 19 | Database design | `docs/er_diagram.mmd`, `docs/VIVA_NOTES.md` (constraints, indexes, transactions) |
| 20-22 | Methodology, NLP, ML | `ml_engine/preprocessing.py` (documented steps), `train.py`, `docs/ml_results.md` |
| 23 | Dataset | `datasets/README.md` (synthetic, reproducible, labelling rules, separate challenge set) |
| 24-25 | Training, evaluation | `docs/ml_results.md` (generated from the stored run) |
| 26 | Implementation | module list in README; screens from the running system |
| 27 | Testing | `docs/TESTING.md` |
| 28 | Results | `docs/ml_results.md`, demo run (`docs/DEMO_SCRIPT.md`), test counts |
| 29 | Security | `docs/SECURITY.md` |
| 30-31 | Limitations, future enhancements | below |
| 32-33 | Conclusion, references | below |

## Functional requirements (as built)
| Requirement | Where |
|---|---|
| Register with email verification code, login (blocked until verified), logout, forgot/reset password with notice emails, edit profile | `accounts` (`otp.py`, `registration.py`, `emails.py`) |
| Structured complaint: area, ward, street, landmark, address, **location chosen by search, map pin or GPS (inside the service area)**, **compulsory photo**, **compulsory description checked for a real municipal issue**, rejected submissions kept as drafts | `complaints/forms.py`, `services/description_check.py`, `core/geo/` | `complaints/forms.py`, `validators.py` |
| NLP + TF-IDF + Multinomial Naive Bayes routing with probabilities and a threshold | `ml_engine`, `complaints/services/routing.py` |
| Human verification queue, corrections, verified-only retraining | `adminpanel`, `complaints/services/corrections.py` |
| Department dashboard: filters, search, sorting, Area > Ward > Street, map | `complaints/views/officer.py`, `filters.py` |
| Assignment to field workers, worker dashboard, status updates, remarks | `complaints/services/workflow.py`, `views/worker.py` |
| Resolution with a mandatory proof photo (`Complaint.resolution_photo`), officer verification, citizen sees the photo with the timeline, confirmation, reopen | `workflow.py`, `transitions.py`, `views/citizen.py` |
| Priority rules, configurable SLA, escalation, notifications | `services/priority.py`, `escalation.py`, `notifications` |
| Feedback after resolution, feedback statistics | `services/feedback.py`, admin dashboard |
| Admin analytics, AI metrics, model training/activation, dataset management | `adminpanel` |
| Users, departments (extensible), SLA settings | `adminpanel` |
| Audit log | `audit`, `adminpanel` |
| Duplicate detection (flag for human review) | `complaints/services/duplicates.py` |
| Explainability (influential terms, stage-by-stage trace) | `ml_engine/explain.py`, "Try the model" page |

## Non-functional requirements
| Quality | How it is met |
|---|---|
| Security | `docs/SECURITY.md` |
| Data integrity | foreign keys, check constraints, transactions, verified on MySQL |
| Maintainability | thin views, service layer, one function for status changes, 461 tests |
| Usability | responsive Bootstrap pages, empty/loading/error states, plain-language citizen view |
| Reliability | a complaint is saved before the model runs; model failure falls back to human verification |
| Explainability | probabilities, influential terms, trace page, stored model version |
| Portability | environment-variable configuration; SQLite for quick checks, MySQL for the project |

## Differences from the synopsis (state these openly)
The synopsis proposed a prototype with three tables, the statuses Pending/In Progress/Resolved, and retraining and notifications as
future work. The implemented system normalises the design to 23 tables, supports a full lifecycle with history, and implements
retraining, notifications, SLA, escalation, feedback and duplicate flagging. Image AI, multilingual support and SMS/email stay future work.

## Limitations to write
- Training data is synthetic; accuracy on a random split of it is optimistic (1.000), the hand-written challenge set gives 0.828.
- Naive Bayes can be confidently wrong; one vague complaint was routed with 0.92 confidence. Human correction exists for this reason.
- English only; stemming is rule-based; keyword priority rules can be gamed and do not understand negation.
- Duplicate thresholds were set from a handful of sample pairs, not a proper evaluation.
- Model training runs inside the web request (about 8 seconds); a background worker is better for larger data.
- No email/SMS delivery; rate limits use local memory; browser-side JavaScript was not covered by automated tests.

## Future enhancements (clearly not implemented)
Email/SMS notifications; image-based classification; Kannada/Hindi complaints with separately measured accuracy; background job
runner for training and SLA checks; real municipal data and periodic retraining; shared cache for rate limits; forced password
change for new staff; mobile app.

## References (use only works you have read)
These appear in the approved synopsis and are real:
1. F. Pedregosa et al., "Scikit-learn: Machine Learning in Python," Journal of Machine Learning Research, vol. 12, pp. 2825-2830, 2011.
2. S. Bird, E. Klein and E. Loper, Natural Language Processing with Python, O'Reilly Media, 2009.
3. Django Software Foundation, Django documentation, https://docs.djangoproject.com/
4. Oracle Corporation, MySQL 8.0 Reference Manual, https://dev.mysql.com/doc/
5. A. McCallum and K. Nigam, "A Comparison of Event Models for Naive Bayes Text Classification," AAAI-98 Workshop on Learning for Text Categorization, 1998.
6. scikit-learn developers, TfidfVectorizer documentation.
Software used without a paper to cite: Bootstrap 5, Leaflet, OpenStreetMap, Pillow, NLTK. Cite their documentation if you mention them.
