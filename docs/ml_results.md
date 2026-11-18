# Machine-learning results: model v1

Trained 07 Nov 2026 02:16. Pipeline: preprocessing, TF-IDF, Multinomial Naive Bayes. **The training data is synthetic (generated), not municipal records.** Figures below are the values measured and stored by the training run.

## Data and split

- Verified training examples: 5097 (ADVERTISEMENTS: 300, ANIMAL_CONTROL: 300, CIVIL_REGISTRATION: 300, EDUCATION: 300, ELECTRICITY: 300, ENVIRONMENT: 300, FIRE: 300, HEALTH: 300, PARKS_GARDENS: 300, PROPERTY_TAX: 300, ROADS: 300, SANITATION: 299, SOCIAL_WELFARE: 299, TOWN_PLANNING: 300, TRADE_LICENCE: 299, TRAFFIC_PARKING: 300, WATER_SUPPLY: 300)
- Stratified split (seed 42): 4077 train / 1020 test
- Best parameters (grid search, cross-validation on the training part only): {'nb__alpha': '0.03', 'tfidf__min_df': '1', 'tfidf__ngram_range': '(1, 2)'}
- Cross-validated macro-F1 on training data: 0.993

## Held-out test split

Accuracy 0.995; macro precision 0.995; macro recall 0.995; macro F1 0.995.

| Department | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| ADVERTISEMENTS | 1.000 | 1.000 | 1.000 | 60 |
| ANIMAL_CONTROL | 1.000 | 1.000 | 1.000 | 60 |
| CIVIL_REGISTRATION | 0.938 | 1.000 | 0.968 | 60 |
| EDUCATION | 0.984 | 1.000 | 0.992 | 60 |
| ELECTRICITY | 1.000 | 1.000 | 1.000 | 60 |
| ENVIRONMENT | 1.000 | 1.000 | 1.000 | 60 |
| FIRE | 1.000 | 1.000 | 1.000 | 60 |
| HEALTH | 1.000 | 1.000 | 1.000 | 60 |
| PARKS_GARDENS | 1.000 | 1.000 | 1.000 | 60 |
| PROPERTY_TAX | 1.000 | 0.983 | 0.992 | 60 |
| ROADS | 1.000 | 1.000 | 1.000 | 60 |
| SANITATION | 1.000 | 1.000 | 1.000 | 60 |
| SOCIAL_WELFARE | 1.000 | 1.000 | 1.000 | 60 |
| TOWN_PLANNING | 1.000 | 0.950 | 0.974 | 60 |
| TRADE_LICENCE | 1.000 | 0.983 | 0.992 | 60 |
| TRAFFIC_PARKING | 1.000 | 1.000 | 1.000 | 60 |
| WATER_SUPPLY | 1.000 | 1.000 | 1.000 | 60 |

Confusion matrix (rows = actual, columns = predicted):

| | ADVERTISEMENTS | ANIMAL_CONTROL | CIVIL_REGISTRATION | EDUCATION | ELECTRICITY | ENVIRONMENT | FIRE | HEALTH | PARKS_GARDENS | PROPERTY_TAX | ROADS | SANITATION | SOCIAL_WELFARE | TOWN_PLANNING | TRADE_LICENCE | TRAFFIC_PARKING | WATER_SUPPLY |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **ADVERTISEMENTS** | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **ANIMAL_CONTROL** | 0 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **CIVIL_REGISTRATION** | 0 | 0 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **EDUCATION** | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **ELECTRICITY** | 0 | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **ENVIRONMENT** | 0 | 0 | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **FIRE** | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **HEALTH** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **PARKS_GARDENS** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **PROPERTY_TAX** | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 59 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **ROADS** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 0 | 0 | 0 |
| **SANITATION** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 0 | 0 |
| **SOCIAL_WELFARE** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 0 | 0 | 0 | 0 |
| **TOWN_PLANNING** | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 57 | 0 | 0 | 0 |
| **TRADE_LICENCE** | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 59 | 0 | 0 |
| **TRAFFIC_PARKING** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 0 |
| **WATER_SUPPLY** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 60 |

Generated sentences share building blocks, so a random split of synthetic data is optimistic by construction. Treat this block as a sanity check, not as the expected real-world accuracy.

## Hand-written challenge set (never used in training)

Accuracy 0.851; macro F1 0.852. By difficulty: hard 0.75 (n=40), normal 0.88 (n=154).

| Department | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| ADVERTISEMENTS | 0.833 | 1.000 | 0.909 | 10 |
| ANIMAL_CONTROL | 0.900 | 0.900 | 0.900 | 10 |
| CIVIL_REGISTRATION | 1.000 | 1.000 | 1.000 | 10 |
| EDUCATION | 0.909 | 1.000 | 0.952 | 10 |
| ELECTRICITY | 0.875 | 0.875 | 0.875 | 16 |
| ENVIRONMENT | 0.818 | 0.900 | 0.857 | 10 |
| FIRE | 0.750 | 0.900 | 0.818 | 10 |
| HEALTH | 1.000 | 0.800 | 0.889 | 10 |
| PARKS_GARDENS | 0.875 | 0.700 | 0.778 | 10 |
| PROPERTY_TAX | 0.833 | 1.000 | 0.909 | 10 |
| ROADS | 0.917 | 0.688 | 0.786 | 16 |
| SANITATION | 0.714 | 0.625 | 0.667 | 16 |
| SOCIAL_WELFARE | 0.833 | 1.000 | 0.909 | 10 |
| TOWN_PLANNING | 0.750 | 0.900 | 0.818 | 10 |
| TRADE_LICENCE | 0.778 | 0.700 | 0.737 | 10 |
| TRAFFIC_PARKING | 0.875 | 0.700 | 0.778 | 10 |
| WATER_SUPPLY | 0.882 | 0.938 | 0.909 | 16 |

Misclassified examples:

| Text | True | Predicted | Confidence |
|---|---|---|---|
| Light at the corner has been dead since Diwali, nobody has come to look | ELECTRICITY | SANITATION | 0.5 |
| A pole fell on the road after last night's wind and the wires are lying across it | ELECTRICITY | PARKS_GARDENS | 0.541 |
| We have not received our water for three mornings in a row | WATER_SUPPLY | SOCIAL_WELFARE | 0.483 |
| Gutter water comes into the house whenever it rains | SANITATION | WATER_SUPPLY | 0.784 |
| The drain in front of the shop is choked with plastic and smells awful | SANITATION | ENVIRONMENT | 0.547 |
| Waste is blocking the drain and the road gets water logged | SANITATION | WATER_SUPPLY | 0.586 |
| The sweeper has not come for two weeks and dry leaves cover the whole street | SANITATION | FIRE | 0.385 |
| The carcass of a cow is rotting beside the road | SANITATION | ANIMAL_CONTROL | 0.305 |
| The garbage vehicle skips our apartment every single day | SANITATION | TRAFFIC_PARKING | 0.852 |
| There is a deep hole outside the school gate and a child fell into it | ROADS | TRADE_LICENCE | 0.501 |
| Cracks are running along the entire stretch of the new road | ROADS | TOWN_PLANNING | 0.676 |
| The metal cover of the drain chamber is missing and a scooter got stuck in it | ROADS | FIRE | 0.184 |
| There is no marking on the crossing in front of the hospital | ROADS | TRADE_LICENCE | 0.649 |
| A road signboard is lying on the ground since the storm | ROADS | ELECTRICITY | 0.427 |
| The rain tree on our road fell last night and is blocking the whole lane | PARKS_GARDENS | ELECTRICITY | 0.455 |
| Benches in the park near the lake are broken so senior citizens cannot sit | PARKS_GARDENS | ENVIRONMENT | 0.235 |
| The walking path inside the park is full of mud after the rain | PARKS_GARDENS | TOWN_PLANNING | 0.287 |
| The dispensary near the bus stand has been shut for a week and old people have nowhere to go | HEALTH | SOCIAL_WELFARE | 0.22 |
| People in our slum have loose motions since two days and the water seems to be the reason | HEALTH | ROADS | 0.323 |
| A shop has pushed its wall onto the lane and the lane has become narrow | TOWN_PLANNING | FIRE | 0.371 |
| The covered market roof leaks and the traders cannot keep their goods | TRADE_LICENCE | EDUCATION | 0.344 |
| The fee they asked for the licence is much higher than the notified amount | TRADE_LICENCE | PROPERTY_TAX | 0.639 |
| The Sunday market spills onto the main road every week and nobody regulates it | TRADE_LICENCE | SANITATION | 0.964 |
| There is a strong smell of gas from the restaurant kitchen next door | FIRE | TOWN_PLANNING | 0.423 |
| A pig family has settled near the open plot behind our flats | ANIMAL_CONTROL | SANITATION | 0.096 |
| The signal at the main junction has been dead for three days and it is chaos | TRAFFIC_PARKING | ADVERTISEMENTS | 0.466 |
| The bus shelter roof has fallen and passengers stand in the rain | TRAFFIC_PARKING | ADVERTISEMENTS | 0.502 |
| The paid parking guys are charging double the fixed rate | TRAFFIC_PARKING | PROPERTY_TAX | 0.854 |
| Builders are dumping debris into the lake bed in the evenings | ENVIRONMENT | SANITATION | 0.435 |

## Confidence threshold

Selected threshold **0.5**, chosen from out-of-fold predictions on the training data (target precision of auto-routed complaints 0.95; target met there: True; floor 0.5).

| Population | Threshold | Auto-routed share | Accuracy of auto-routed |
|---|---|---|---|
| test | 0.5 | 100% | 0.995 |
| challenge | 0.5 | 86% | 0.922 |

A high confidence is not a guarantee: Naive Bayes can be confidently wrong, which is why complaints can be corrected by an administrator and why only verified corrections are used for retraining.
