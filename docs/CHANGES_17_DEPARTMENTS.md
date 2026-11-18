# Seventeen departments (was four)

## The problem
The system was trained for Electricity, Water Supply, Sanitation and Roads only. A municipality has many more departments, so a citizen
reporting a stray-dog bite, a wrong property-tax bill or a missing birth certificate had nothing to be routed to, and **the description
check refused those complaints** (100 of the 194 hand-written test complaints for the new departments were refused before this change).

## What is now supported
| # | Department | Code | Typical complaints |
|---|---|---|---|
| 1-4 | Electricity, Water Supply, Sanitation, Roads | `ELECTRICITY` ... `ROADS` | (unchanged) |
| 5 | Parks & Gardens | `PARKS_GARDENS` | fallen or dangerous trees, park and playground upkeep |
| 6 | Public Health | `HEALTH` | health centres, vaccination, fogging, dengue, food safety |
| 7 | Town Planning & Buildings | `TOWN_PLANNING` | illegal construction, plan approval, unsafe buildings, encroachment of public land |
| 8 | Property Tax & Revenue | `PROPERTY_TAX` | wrong bills, assessment, khata, receipts |
| 9 | Trade Licence & Markets | `TRADE_LICENCE` | licences, vendors, municipal markets |
| 10 | Fire & Emergency | `FIRE` | hydrants, fire exits, rescue |
| 11 | Animal Control | `ANIMAL_CONTROL` | stray dogs, cattle, monkeys, dog bites |
| 12 | Municipal Education | `EDUCATION` | municipal schools, anganwadis |
| 13 | Social Welfare | `SOCIAL_WELFARE` | pensions, schemes, scholarships, shelters |
| 14 | Birth, Death & Marriage Registration | `CIVIL_REGISTRATION` | certificates and records |
| 15 | Traffic & Parking | `TRAFFIC_PARKING` | signals, parking, bus shelters |
| 16 | Environment & Lakes | `ENVIRONMENT` | lake, air and noise pollution, factory smoke |
| 17 | Advertisements & Hoardings | `ADVERTISEMENTS` | illegal hoardings, banners, posters |

Where two departments could both be argued, the rule used for the training data is written at the top of `ml_engine/issues_extra.py`
(for example: mosquito breeding in stagnant water is Sanitation, a request for fogging is Health). State this in the report.

## What changed (no screen, template or script was touched: `templates/` and `static/` are identical to the previous version)
| Area | Change |
|---|---|
| Master data | `seed_master_data` creates the 17 departments (and, with `--demo-users`, two officers and two field workers for each). Safe to run again: it only adds what is missing and never edits or re-enables a department you changed. |
| Training data | `datasets/complaints_synthetic_v2.csv`: 17 x 300 synthetic examples. The old four-department file is unchanged. Everyday-speech phrasings were added for all 17 ("we lost current", "taps are dry"). |
| Test sets | `challenge_set_v2.csv` (the original 64 + 130 new hand-written complaints) and `challenge_set_v3.csv` (51 written before the final training data was added). Neither is ever used for training. |
| Description check | The municipal vocabulary covers all 17 departments; text the vocabulary does not recognise but the trained model clearly does is now accepted (a second opinion). Out-of-scope matters (ration card, passport, driving licence, bus service) are still refused. |
| Priority | New rules: animal attack or rabies (High), disease outbreak (High), person trapped / rescue needed (Critical). |
| Commands | `evaluate_model <csv>` scores the active model on any labelled file. |

## Measured results (synthetic training data; small hand-written test sets, so indicative only)
| Measure | Result |
|---|---|
| Held-out split of the synthetic data | 0.995 (optimistic: generated sentences share building blocks) |
| 194 hand-written complaints, all 17 departments | **85.1%** (normal 88%, hard 75%) |
| The original 64 hand-written complaints | 78.1% (it was 82.8% when only four departments existed: more departments means more confusion) |
| 51 complaints written before the final training data was added | **94.1%** (it was 86.3% before the everyday-speech phrases) |
| Complaints routed automatically at threshold 0.5 (challenge set) | 86% of them, of which 92.2% were right; the rest go to a person |
| Description check on fresh valid complaints, vocabulary only | refused 8.8% and 17.6% on two fresh sets of 34 |
| Description check, vocabulary plus trained model | refused 0% on a third fresh set of 34 and 5.9% on the earlier one; junk accepted 0 of 16 and 0 of 16 |
| Time to train all 17 departments | about 25 seconds |

Treat these as indicative: every test set was written by the project author, and each was used to improve the system after it was first
measured (the numbers above say which were fresh at the time). Real municipal complaints will behave differently; collect and verify real
ones and retrain (the admin AI page already supports corrections and imports).

## Known limits
- **Synthetic data.** The system has never seen a real citizen complaint.
- **Confusable pairs.** Most mistakes are between neighbours: Roads / Traffic, Sanitation / Environment / Health, Parks / Roads (fallen trees), Town Planning / Roads (encroachment). Low-confidence cases go to the verification queue.
- **Informal wording.** Short or very colloquial complaints are the weakest area.
- **The description check accepts some in-topic text that is not a complaint** (for example a school-related remark), because the trained model recognises its words. The department's staff can close it.
- **Vocabulary has to follow the departments.** `complaints/municipal_terms.py` lists the everyday words per department; a new department also needs its words there.
- Training runs inside the web request (about 25 s for 17 departments); use `python manage.py train_complaint_model --activate` on a real server whose request time limit is 30 s.

## Applying this to an existing installation (keeps your data)
```bash
python manage.py migrate                         # nothing new to migrate, harmless to run
python manage.py seed_master_data                # adds the 13 new departments (add --demo-users --password ... in development for staff)
python manage.py import_dataset datasets/complaints_synthetic_v2.csv --source SYNTHETIC --dataset-version synthetic_v2
python manage.py train_complaint_model --activate
python manage.py evaluate_model datasets/challenge_set_v3.csv     # optional: check the result
```
Existing users, complaints, departments and models are not changed. The old model stays in the AI page's history until the new one is activated.

Tested on MySQL 8 by building a database with only the four original departments and applying exactly these commands: the original four kept
their ids and descriptions, 13 were added, and the 17-department model trained in 21 seconds. One difference to know about: on an upgraded
installation the original four departments keep their older training examples as well as the new ones (about 510 rows each instead of 300), so
they are slightly favoured. In that test the 194 hand-written complaints scored 82.5% instead of the 85.1% above, and the 51 fresh complaints
scored the same 94.1%. A fresh installation gets the balanced result.

## Adding department number 18 later
1. Admin panel, *Departments*, add it (name, code, description). Give it officers and workers (*Users*).
2. Add 40 or more example complaints for it (*AI model*, add or import examples) and train a new model.
3. Add its everyday words to `complaints/municipal_terms.py`, otherwise its complaints may be refused as unclear.
4. Optionally add hand-written test complaints to the challenge file and run `evaluate_model`.
