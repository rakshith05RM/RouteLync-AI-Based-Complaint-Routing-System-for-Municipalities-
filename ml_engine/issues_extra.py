"""
Problem phrases for the departments added after the first four (SYNTHETIC training data, written by the project author).

Labelling conventions where two departments could both be argued (state these in the report):
  * mosquito breeding in stagnant water, dead animals, burning of garbage, drain overflow   -> SANITATION
  * a request for fogging/vaccination, a dengue or cholera outbreak, food safety             -> HEALTH
  * tree or branch fallen/dangerous, park and playground upkeep                              -> PARKS_GARDENS
  * stray dogs, cattle, monkeys, dog bites, sterilisation                                    -> ANIMAL_CONTROL
  * traffic signals, parking, bus shelters                                                   -> TRAFFIC_PARKING
  * potholes, footpath damage, speed breakers, road signs and markings                       -> ROADS
  * hoardings, flex banners, posters                                                         -> ADVERTISEMENTS
  * lake/river pollution, air and noise pollution, factory smoke or effluent                 -> ENVIRONMENT
  * illegal buildings, plan approval, unsafe buildings, encroachment of public land          -> TOWN_PLANNING
  * fire hazards, hydrants, rescue                                                           -> FIRE
  * bills, assessments, khata, tax receipts                                                  -> PROPERTY_TAX
  * trade licences, vendors, municipal markets                                               -> TRADE_LICENCE
  * municipal schools and anganwadis                                                         -> EDUCATION
  * pensions, welfare schemes, scholarships, shelters for the homeless                       -> SOCIAL_WELFARE
  * birth, death and marriage certificates and records                                       -> CIVIL_REGISTRATION
"""

ISSUES_EXTRA = {
    "PARKS_GARDENS": [
        "The park is not being maintained", "The grass in the park is overgrown", "The park benches are broken",
        "A tree has fallen across the road", "A large tree branch is hanging dangerously", "The tree needs to be trimmed",
        "A dry tree is about to fall", "Trees are being cut illegally", "Tree branches are covering the street lamp",
        "The children's play equipment is broken", "The swings in the playground are damaged", "The playground has not been maintained",
        "The park gate is kept locked all day", "The fountain in the park is not working", "The garden plants have dried up",
        "The park has no drinking water facility", "The saplings were not planted as promised", "The jogging track in the park is damaged",
        "The park boundary wall has collapsed", "Weeds have grown all over the garden", "The fallen tree trunk has not been removed",
        "The lawn is not being watered", "The open gym equipment in the park is broken", "A tree is leaning over our house",
        "Please plant more trees in our area", "The tree guards are broken", "The avenue trees along the road are dying",
        "The park has been closed for months", "The gardener is not coming to the park", "Overgrown bushes are blocking the view at the turn",
        "A dead tree on the roadside needs removal", "The park pathway is muddy and slippery", "The seesaw in the children's park is rusted",
        "The roots of the big tree are lifting the compound wall",
    ],
    "HEALTH": [
        "The primary health centre has no doctor", "The dispensary is closed during working hours", "Medicines are not available at the health centre",
        "The urban health centre is in an unhygienic condition", "A vaccination camp was not held in our area", "Children have not received their vaccines",
        "Dengue cases are rising in our locality", "Fogging has not been done in our area", "We request anti malaria spraying in our lane",
        "Several people have fallen ill with fever in our street", "There is a cholera outbreak in our colony", "Food items are being sold after the expiry date",
        "Adulterated food is being sold in the shop", "The hotel is serving stale food", "The street food stall near the school is unhygienic",
        "The meat shop is operating in unhygienic conditions", "Ambulance service is not available", "The health worker has not visited our house",
        "Pregnant women are not getting health checkups", "There is no staff in the maternity ward of the municipal hospital",
        "The municipal hospital is charging money for free services", "The municipal hospital has no beds available", "Blood test reports are delayed at the health centre",
        "Free medicines are being sold outside", "The nurses are absent at the health centre", "Please arrange a health camp in our ward",
        "Tuberculosis patients are not getting their medicines", "Polio drops were not given to our children", "An eye checkup camp is needed for senior citizens",
        "Typhoid cases are spreading in the slum", "The fogging machine has not come to our lane", "The health inspector has not inspected the restaurants",
    ],
    "TOWN_PLANNING": [
        "Illegal construction is going on next door", "The building is being constructed without a permit", "The construction is violating the sanctioned plan",
        "Extra floors are being built beyond the approved plan", "The neighbour has encroached on public land", "Government land is being occupied illegally",
        "A compound wall has been built on the road space", "The old building is in a dangerous condition and may collapse", "The cracked building is leaning dangerously",
        "The building plan approval is pending", "The building plan sanction has been delayed for months", "The occupancy certificate is not being issued",
        "The commencement certificate application is stuck", "The shop owner has extended the shop onto public land", "An unauthorised layout is being developed",
        "The builder is not leaving the mandatory setback", "A commercial building is being run in a residential area", "The site plan approval has not been given",
        "The apartment is being built without parking space", "Request for demolition of the unsafe building", "The land use conversion application is pending",
        "Basement excavation is damaging the neighbouring houses", "The neighbour is encroaching on our plot boundary", "A building has blocked the planned road",
        "Request for regularisation of my building", "The builder has not completed the park as per the sanctioned plan", "An illegal shed has come up on public land",
        "The plan violation has been reported but no action was taken", "A tall building is being built without clearance", "The town planning officer is not responding to our complaint",
    ],
    "PROPERTY_TAX": [
        "The property tax bill is wrong", "Property tax has been charged twice", "The tax amount shown is much more than last year",
        "My property tax payment is not showing in the system", "The tax receipt has not been issued after payment", "The online property tax portal is not working",
        "The property assessment is incorrect", "The built up area is wrongly recorded", "The khata certificate is not being issued",
        "The khata transfer has been pending for months", "Please correct the owner name in the tax records", "A tax demand notice was wrongly sent to me",
        "I paid the property tax but still got a notice", "A penalty has been added wrongly to my tax", "Interest is charged even though I paid on time",
        "The rebate for early payment was not given", "The tax for the vacant plot is wrongly calculated", "Our house is charged commercial tax though it is residential",
        "There is no acknowledgement for the tax appeal", "Property tax arrears are wrongly shown", "The tax officer is asking for a bribe to correct the bill",
        "The mutation of property has not been done", "The self assessment form was rejected without reason", "A duplicate tax receipt is needed but not provided",
        "The tax exemption for senior citizens is not applied", "The assessment number is not found in the portal", "Water tax and property tax are mixed up in my bill",
        "The refund of excess tax paid is pending", "The tax bill has the wrong address", "I did not receive the property tax bill",
    ],
    "TRADE_LICENCE": [
        "The trade licence renewal is pending", "The trade licence application has been delayed", "The licence for my shop is not being issued",
        "The fee for the trade licence is wrongly charged", "A shop is running without a trade licence", "The licence inspector is demanding money",
        "Street vendors do not have a vending certificate", "The vending zone has not been marked", "Please issue a vending licence for my cart",
        "The market stalls are not allotted properly", "The market shop allotment is unfair", "Stall rent is being collected twice",
        "The weekly market is held on the main road", "The municipal market building is in poor condition", "The market has no proper shed for the vendors",
        "The licence for my eating house is not renewed", "The factory is running without a licence", "The licence for my bakery was cancelled without notice",
        "The licence renewal website is not working", "Mobile vendors are selling without a licence", "Unlicensed vendors are selling near the school gate",
        "The market lease has not been renewed", "I request shifting of my stall", "Illegal shops have come up beside the market",
        "The licence fee receipt was not given", "The licence certificate has the wrong shop name", "I need a duplicate trade licence",
        "The hawkers are not being rehabilitated", "The market association complains about unfair stall fees", "Vendors from outside are taking our market space",
    ],
    "FIRE": [
        "The fire hydrant is not working", "There is no fire hydrant in our area", "The fire extinguishers in the building have expired",
        "The building has no fire exit", "The fire exit is blocked in the commercial complex", "A fire has broken out in the warehouse",
        "Fire is spreading in the dry grass", "Smoke is coming out of the closed shop", "The fire engine took too long to reach us",
        "The fire safety certificate for the hotel is not renewed", "The cinema hall has no fire safety arrangements", "LPG cylinders are stored dangerously in the shop",
        "Gas cylinders are kept in the narrow lane", "Illegal firecracker storage in a residential area", "A firecracker godown is operating near the houses",
        "The fire station in our area has no staff", "The fire lane is blocked by parked vehicles", "The fire hose pipe has been stolen",
        "Please conduct a fire safety inspection", "Please arrange a fire drill in our apartment", "The apartment fire alarm is not working",
        "An electric short circuit has caused a fire", "A person is trapped in the collapsed wall and rescue is needed", "A flood rescue boat is needed in our colony",
        "A snake has entered the house and rescue is needed", "A gas leak has been reported in the building", "A beehive on the building needs to be removed",
        "The firefighting water tank is empty", "Emergency rescue is needed after the building collapse", "A person is stuck in the lift and needs rescue",
    ],
    "ANIMAL_CONTROL": [
        "Stray dogs are attacking people", "A pack of stray dogs is chasing children", "A stray dog has bitten a child",
        "There is a stray dog menace in our colony", "Dogs chase vehicles at night", "Please arrange dog sterilisation in our area",
        "The stray dog population is increasing", "A rabid dog is roaming in the lane", "Anti rabies vaccination for stray dogs has not been done",
        "Cattle are roaming freely on the road", "Cows are blocking the road", "A bull is attacking people",
        "Pigs are roaming in the colony", "Monkeys are entering the houses", "There is a monkey menace in our locality",
        "Buffaloes are tied on the roadside", "The cattle shed in the residential area is a nuisance", "An illegal dairy is running in the apartment area",
        "The neighbour's pet dog is aggressive and not controlled", "Please register pet dogs in our ward", "The animal shelter is not responding",
        "An injured stray dog needs treatment", "An injured cow is lying on the road", "Dog bite victims are not getting treatment",
        "Goats are grazing in the park", "Dogs fight at night and people cannot sleep", "Please catch the stray dog in our street",
        "The dog catching van has not come", "Stray dogs are chasing the school children", "A herd of cattle is sitting at the junction",
    ],
    "EDUCATION": [
        "The municipal school building is in poor condition", "The school roof is leaking", "The school has no toilets for girls",
        "The school has no drinking water", "The teachers are absent from the municipal school", "There is no teacher for mathematics in the school",
        "The mid day meal is not served", "The mid day meal quality is very poor", "The school has no benches for the children",
        "Textbooks have not been distributed", "School uniforms were not given", "The school compound wall is broken",
        "The school playground is unusable", "The municipal school was closed without notice", "Admission to the municipal school is being refused",
        "The headmaster is demanding money for admission", "The school library has no books", "The computer lab in the school is not working",
        "The anganwadi centre is not functioning", "The anganwadi does not provide food to the children", "The school bus is not available for the students",
        "A teacher is beating the children", "The children are not getting free books", "The school building is being used for other purposes",
        "The school has no sports teacher", "The school kitchen is dirty", "We need more classrooms in the municipal school",
        "The school building is damaged and unsafe for children", "The pre primary section is not working", "The school has no science teacher",
    ],
    "SOCIAL_WELFARE": [
        "My old age pension has not been credited", "The widow pension has stopped", "The disability pension is delayed",
        "The pension amount was reduced without notice", "The application for old age pension is pending", "I need help with the disability certificate",
        "The disability certificate application was rejected", "The scholarship amount has not been received", "The scholarship form was rejected without reason",
        "The welfare scheme benefits are not reaching us", "The housing scheme application is pending", "I applied for the subsidised house but got no reply",
        "The self help group loan is not sanctioned", "The women's self help group has not received the grant", "Please issue a below poverty line certificate",
        "The income certificate is not being issued", "The caste certificate application is pending", "The free sewing machine scheme application is pending",
        "The senior citizen card is not issued", "The old age home is not providing proper food", "A homeless person is living on the street and needs shelter",
        "Homeless people are sleeping on the footpath without a shelter", "The night shelter is closed", "The community kitchen is not providing meals",
        "The social welfare officer is not responding", "The pension office is asking for a bribe", "The compensation for the family has not been paid",
        "The maternity benefit has not been received", "I applied for the pension months ago but nothing happened", "The welfare scheme money is being deducted wrongly",
    ],
    "CIVIL_REGISTRATION": [
        "The birth certificate has not been issued", "The birth certificate application is pending for a month", "There is a spelling mistake in the birth certificate",
        "The name is wrong in the birth certificate", "Please add the child's name to the birth record", "The death certificate is not being issued",
        "The death certificate application is delayed", "The date of birth is wrong in the certificate", "The marriage registration is pending",
        "The marriage certificate has not been issued", "The marriage registration office is closed", "A duplicate birth certificate is needed",
        "The registrar is asking for extra money", "The online birth registration is not working", "The registrar never received the birth details from the hospital",
        "Late registration of birth is being refused", "The parent's name is missing in the certificate", "A correction in the death certificate is needed",
        "The certificate has the wrong gender", "The registrar office staff are rude and not helpful", "There is a long queue and no token system at the registrar office",
        "The certificate was issued with the wrong date", "The name change application is pending", "The application for the family certificate is pending",
        "The nativity certificate is not issued", "The certificate is not available online even after approval", "The death registration for my father is not done",
        "My newborn's birth was not registered", "No marriage registration slot is available", "The certificate sent by post did not arrive",
    ],
    "TRAFFIC_PARKING": [
        "The traffic signal is not working", "The traffic light is stuck on red", "The signal timing is wrong and causes jams",
        "There is no traffic signal at the busy junction", "The pedestrian signal is not working", "Vehicles are parked illegally on the road",
        "Cars are parked on the footpath", "Parking on both sides of the road is blocking traffic", "There is no parking space near the market",
        "The paid parking contractor is overcharging", "There is a heavy traffic jam every evening at the junction", "Heavy trucks are entering the area during the day",
        "Heavy vehicles are using the residential road", "The one way sign is missing", "The no parking board has been removed",
        "Vehicles are driving the wrong way on the one way road", "The bus shelter is broken", "There is no bus shelter at the stop",
        "The bus stop sign is missing", "Auto rickshaws are blocking the bus stop", "We need a pedestrian crossing near the school",
        "The flashing signal at the crossing is not blinking", "Vehicles are being towed without notice", "The tow truck is damaging vehicles",
        "Abandoned vehicles have been lying on the road for months", "Illegal parking in front of my gate", "The parking fee receipt is not given",
        "The multi level parking is closed", "A bike taxi stand is blocking the lane", "The traffic police are not present during the peak hours",
    ],
    "ENVIRONMENT": [
        "The lake is being polluted with sewage", "Froth and foam are seen in the lake", "Dead fish are floating in the lake",
        "The lake is covered with weeds", "The lake has been encroached", "Construction waste is being dumped into the lake",
        "The lake bund is damaged", "Industrial smoke is polluting the air", "A factory is releasing black smoke",
        "Air pollution from the brick kiln is very high", "The factory discharges chemical waste into the drain", "Chemical effluent is being released into the lake",
        "Dust from construction is polluting the air", "There is loud music from the function hall at night", "The noise from the factory is unbearable",
        "Loudspeakers are being used late at night", "There is noise pollution from the pub near our house", "The generator noise is disturbing the residents",
        "Burning of tyres is polluting the air", "There is a foul odour from the chemical factory", "The river is being polluted",
        "The canal water is black and smelly", "The rajakaluve is encroached", "The plastic ban is not enforced in the market",
        "Single use plastic is being sold openly", "Please inspect rainwater harvesting in our area", "The air quality in our area is very poor",
        "Smoke from the crematorium is bothering us", "The lake water has turned green and stinks", "The sewage treatment plant is releasing untreated water into the lake",
    ],
    "ADVERTISEMENTS": [
        "An illegal hoarding has come up on the roadside", "The hoarding is dangerously large and may fall", "The hoarding is blocking the view at the junction",
        "Unauthorised banners are tied to the poles", "Political flex banners are covering the road", "Illegal posters cover the walls near the bus stand",
        "Illegal posters have been stuck on the public wall", "The advertisement board was built without permission", "A big billboard is on the roof of the building without a licence",
        "The hoarding has collapsed on the road", "The hoarding is hanging loose after the wind", "The LED screen advertisement is distracting drivers",
        "Advertisements are painted on the school wall", "The advertisement tax is not being collected", "Unlicensed shop signboards are covering the footpath",
        "The shop board extends onto the road", "Flex boards are nailed to the trees", "The banners for the function were not removed after the event",
        "The old torn flex is still hanging on the pole", "Illegal advertising on the bus shelter", "The unipole advertisement structure is unsafe",
        "The ad agency has not removed the expired hoarding", "Hoardings have been installed on the footpath", "An illegal digital hoarding has come up near the school",
        "Please remove the illegal flex boards", "Bills are stuck on the bridge pillars", "The hoarding blocks the sunlight to our house",
        "The big board on the terrace may fall during the rainy season", "Pamphlets and stickers are pasted on every wall in our lane", "A giant banner is covering the traffic signal",
    ],
}


# Everyday-speech phrasings for ALL seventeen departments (the original four included). People rarely write "the streetlight
# is not functioning"; they write "we lost current" or "taps are dry". Used only by synthetic_v2 (synthetic_v1 is unchanged).
ISSUES_COLLOQUIAL = {
    "ELECTRICITY": [
        "We lost current in the whole lane", "No current since morning", "Current has gone again and it is very hot", "The pole light near our entrance has stopped",
        "Our street is completely dark after sunset", "The light on the pole near my house has fused", "The bulb in the street lamp is dead",
        "Power is gone in half of our apartment", "The lineman has not come to fix the power", "An electric wire fell down in the rain",
        "The pole near the school is giving sparks", "Voltage drops every evening and the fan runs slow", "The transformer buzzes loudly and smoke comes out",
        "The building has had no electricity since yesterday evening"],
    "WATER_SUPPLY": [
        "Taps are dry in our house", "Our tap gave no water today", "We did not get any water this week", "Water is coming very slowly",
        "The water supplied looks muddy and stinks", "A water main is damaged and a stream runs on the street", "We get water only for ten minutes",
        "The sump is empty because there is no supply", "The connection pipe is leaking in front of our gate", "The borewell motor has stopped and we have no water",
        "The valve near the road leaks clean water all day", "The supply timing keeps changing and we miss the water", "Low pressure and the overhead tank never fills"],
    "SANITATION": [
        "Nobody has collected the waste from our lane", "Waste is lying on the road for days", "The bin is full and spilling onto the road",
        "The nala near my shop is blocked and dirty water spreads", "Black dirty water is flowing on the road", "There is a bad smell from the drain",
        "The sweeper does not come to our lane", "Rotten waste is lying behind the hall and smells", "The public toilet has no water and is filthy",
        "The sewer is overflowing near our gate", "The septic tank van has not come", "Plastic and garbage are piled near the nala",
        "Flies and mosquitoes are everywhere because of the dump"],
    "ROADS": [
        "A pit in the road is causing accidents", "The road has many pits and bikes slip", "Trench work on the road was left unfinished", "The road work was left half finished",
        "Walkway tiles are loose and broken", "The road surface has come off in patches", "A water filled pit on the road is dangerous",
        "The manhole lid is open on the road", "The bump on the road is too high", "No lane markings or zebra lines are visible",
        "The divider is broken after the accident", "The bridge approach is sinking", "The road edges have crumbled and vehicles slip"],
    "PARKS_GARDENS": [
        "A tree is tilting dangerously towards the road", "The tree near the wires needs cutting", "The colony park is always closed", "The park has no swings or benches",
        "The plants in the park are dead", "The young plants along the road have withered", "A tree fell after the rain and blocked the lane",
        "Branches are touching our balcony", "Please cut the dangerous dry branches", "The garden has turned into a jungle",
        "The play area for children is in bad shape", "The tap in the park is broken and the plants are dying", "A tree trunk has been lying on the roadside for days"],
    "HEALTH": [
        "Many people have fever in our area", "We need mosquito fogging in our locality", "The health centre gives no medicines", "There is no doctor at the dispensary today",
        "The bakery sells stale items", "People got a stomach infection after eating at the stall", "The vaccine is not available at the clinic",
        "The government hospital has no beds", "Children keep falling sick in our lane", "The medical shop sells expired medicine",
        "Medicines for chronic illness are not given at the clinic", "The clinic staff are rude and do not treat poor patients", "A health camp is needed in our area"],
    "TOWN_PLANNING": [
        "A building is coming up over the pedestrian path", "The neighbour is building without permission", "The site has no sanction signboard", "A weak old house nearby seems about to fall",
        "The owner refuses to repair the dangerous building", "The builder has taken the road space for the building", "The new building has no parking",
        "Illegal floors are being added", "A compound wall is built on public land", "My plan approval file is stuck",
        "A warehouse is running inside a residential area", "Work continues at night without sanction"],
    "PROPERTY_TAX": [
        "The name on the tax receipt is not mine", "Payment was debited from my bank but the system says unpaid", "The tax bill has increased wrongly", "The area of my house is entered wrongly in the tax system",
        "The assessment is wrong for my house", "The online tax payment failed and the bill is pending", "I got a tax notice after paying",
        "The tax office is not correcting my name", "The tax is calculated at the wrong rate", "There is no receipt for the tax I paid",
        "The khata is not transferred to my name", "My house is wrongly shown as commercial"],
    "TRADE_LICENCE": [
        "My shop licence renewal is stuck", "The licence office keeps delaying my file", "Hawkers have blocked the gate of the market", "Genuine shopkeepers are losing business to hawkers",
        "The shop I took on rent from the corporation is in a bad condition", "A shop is running without a licence", "The inspector wants a bribe for my licence",
        "I need a licence for a small stall", "Vendors have no place allotted in the market", "The market has no shed for the traders",
        "A new licence application has been pending for weeks", "The rent receipts for my market stall are not being given"],
    "FIRE": [
        "The extinguishers have not been refilled", "The exit door of the building is stuck", "Fire has started in the dry leaves near the houses", "The fire hydrant cover is missing",
        "There is no fire safety in the shopping complex", "Gas cylinders are kept in the lane", "The fire engine did not reach on time",
        "Smoke is coming out of the building", "A short circuit has started a fire in the shop", "Help is needed to rescue a person stuck inside",
        "A snake has come into our house and needs to be caught", "The fire alarm in our flats is not working"],
    "ANIMAL_CONTROL": [
        "Street dogs attacked a passer-by near our gate", "Dogs bite people who walk in the morning", "Cows keep sitting at the crossroad in the evenings", "Cattle are sitting in the middle of the road",
        "Monkeys snatch food from the houses", "Monkeys are troubling the residents", "Many street dogs have come into our lane",
        "A dog has bitten a child and we need help", "The dog van should take away the aggressive dogs", "The dogs are not vaccinated and we fear rabies",
        "A bull is running on the street and scaring people", "Injured animals are lying on the roadside"],
    "EDUCATION": [
        "There are not enough desks in the classrooms", "The midday meal has not been served for a long time", "Teachers are often absent from the classes", "The school has no toilets for the children",
        "The classroom roof is leaking in the rain", "The corporation school has no teachers for some subjects", "Children do not get books in the school",
        "The school building is in a very bad state", "The school ground is full of weeds", "The anganwadi does not open on most days",
        "Admission is being refused at the corporation school", "The teachers do not teach properly in the school"],
    "SOCIAL_WELFARE": [
        "My pension was discontinued suddenly", "I did not receive my pension for many months", "My son's scholarship form has had no response", "My application for the scheme is pending for a year",
        "The shelter for the homeless is closed", "The homeless have no place to stay since the shelter shut", "The welfare office did not help with my form",
        "The disability certificate is not given", "The income certificate is stuck", "The benefit money for my family has not come",
        "The widow pension is not credited", "The senior citizen card is not given"],
    "CIVIL_REGISTRATION": [
        "The registrar returned my application without explanation", "My child's birth is not registered yet", "We paid for a death certificate but it never came", "There is a mistake in the name on my certificate",
        "Spelling is wrong in the marriage record", "The birth record has a wrong date", "The registrar office is always closed",
        "I need to correct my certificate and no one helps", "The certificate has not come by post", "The certificate download is not working",
        "The registrar asks for money to issue the certificate", "My application for the registration of marriage is stuck"],
    "TRAFFIC_PARKING": [
        "The signal lights give conflicting signals", "The signal is not working at the junction", "Two wheelers occupy the walkway", "Vehicles are parked on both sides of our narrow lane",
        "Our bus stop has no sign so buses skip it", "Buses do not stop at our bus stop", "The pedestrian crossing is missing near the school",
        "There is a long traffic jam every morning here", "The parking attendant takes extra money", "Autos stand on the road and block the traffic",
        "A vehicle has been parked in front of our gate for days", "The traffic signal timing is not proper"],
    "ENVIRONMENT": [
        "Factory fumes are irritating our eyes and throat", "The lake water looks like green paint", "The lake smells awful", "The party hall blasts speakers late into the night",
        "Noise from the DJ party disturbs us", "Dust and smoke from the kiln spoil the air", "The factory releases dirty water into the lake",
        "Fish are dying in the lake", "The air in our area has a chemical smell", "Plastic is being burnt near the lake",
        "The generator noise disturbs the whole night", "The canal water has turned black"],
    "ADVERTISEMENTS": [
        "A huge banner hangs over the road from two poles", "The banner is swinging and may fall", "Cinema posters have been stuck on boundary walls", "The rooftop board near the junction is dangerous",
        "Banners are tied to every pole in our street", "Posters cover our compound wall", "The shop board is hanging over the footpath",
        "An illegal board was put up without permission", "Old banners are not removed after the event", "A giant screen advertisement is distracting drivers",
        "The board is nailed to the tree", "The hoarding blocks the view at the turn"],
}
