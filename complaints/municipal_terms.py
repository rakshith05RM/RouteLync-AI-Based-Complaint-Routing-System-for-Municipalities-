"""
Hand-written vocabulary of what RouteLync can handle. It is deliberately visible and editable: the check that uses it
(complaints/services/description_check.py) can be explained in one sentence, which a statistical model cannot.

STRONG terms name something that is itself a municipal problem or a specific piece of municipal infrastructure
("pothole", "garbage", "transformer"). WEAK terms are ordinary words that only mean a municipal problem together with
a problem word ("road", "water", "light" + "broken", "no", "leaking" ...). Words are matched after the same stemming the
classifier uses, so "potholes" and "pothole" are the same.

Scope = the departments the application supports (seventeen in the standard setup: electricity, water, sanitation, roads, parks,
health, town planning, property tax, trade licences, fire, animal control, education, social welfare, civil registration, traffic and
parking, environment, advertisements). Anything listed in OUT_OF_SCOPE is a municipal-sounding matter RouteLync does not handle.
When a department is added to the system, add its everyday words here, otherwise its complaints would be refused as unclear.
"""
STRONG = """
streetlight streetlights lamppost transformer electrocution sparks sparking blackout
pothole potholes manhole footpath pavement speedbreaker culvert flyover crater craters trench asphalt zebra
garbage trash rubbish litter dustbin dumpster sewage sewer sewerage gutter nala drainage waterlogging septic rubble carcass
pipeline borewell mosquito mosquitoes stench debris
playground saplings gardener hydrant hydrants extinguisher extinguishers hoarding hoardings billboard flex stray rabies rabid sterilisation sterilization
dengue malaria fogging vaccination vaccine epidemic outbreak anganwadi midday khata assessment registrar sanction sanctioned setback demolition encroachment encroached
effluent scum pollution pollutant unauthorised unauthorized hawkers vending
monkey monkeys pig pigs cattle bull bulls tax taxes licence license arrears zoning
""".split()

WEAK = """
road roads street lane light lights lamp bulb pole wire wires cable cables power electricity electric voltage current meter fuse
water tap taps pipe pipes supply tank pressure leak leaking leakage drinking
waste smell toilet toilets sweep sweeping stink dirty dump flood flooding stagnant
crack cracks bridge divider signboard junction drain drains hole holes bump bumps marking markings crossing bin bins bag bags worms insects mud muddy rust
tree trees branch branches park garden lawn bench benches
school teacher teachers classroom classrooms meal anganwadi
dog dogs cow cows cattle monkey monkeys bull bulls pig pigs
health hospital clinic dispensary doctor doctors medicine medicines food fever vaccination
building construction permit permission wall plot shop shops market stall stalls vendor vendors
tax bill receipt certificate certificates birth death marriage pension scholarship licence license shelter
fire smoke cylinder cylinders gas exit alarm
signal signals traffic parking parked
lake factory kiln noise music loud speaker speakers generator air
board boards banner banners poster posters ad ads advertisement advertisements screen
godown crackers firecrackers portal rate commercial residential fee fees inspector
truck trucks lorry lorries vehicle vehicles car cars tyre tyres plastic
headmaster admission donation welfare scheme schemes card maternity assistance benefit benefits compensation grant application
""".split()

# Words that say something is wrong. "no" and "not" matter ("no water", "not working").
PROBLEM = """
broken broke damaged damage leak leaking leaks leakage blocked block blockage choked clogged overflow overflowing overflows
burst missing stopped stop failed failure fail dead dark flickering flicker fallen fell collapsed cracked crack
dirty foul smelly stink stinking stagnant flooded flooding no not never without off cut outage unsafe dangerous
uncollected pile piled scattered accumulated accumulating pending irregular low high loose hanging exposed sparking
dim dry dried rusty foamy spraying running spilling filthy rotting lying dumped tripping deep big huge nobody keeps barely lost tearing scraping
caved cave burning burnt smoke vanished faded worn full flowing heap crowded smell insects worms
wrong delay delayed delays rejected reject refuse refused stuck incorrect error mistake excess extra absent closed shut illegal illegally
bite bitten attack attacked attacking chasing aggressive expired stale rotten adulterated unhygienic sick ill tilting leaning
jam jams noisy polluted polluting foam locked empty pasted stuck bribe bribes demanding overcharging charged charging
twice double wasting wasted leaking choking cough coughing irritating
trim prune hiding blocking pushed narrow occupy occupying occupied unpaid renewal renew higher excessive unfair stacked stored caught
drip drips dripping donation donations nothing pay paying ban banned abandoned loud loudly noise cover covering covered tied nailed nails
distract distracts distracting bright infection infected poisoning cash smell
cloudy pain painful falling pieces blinking flashing
""".split()

OUT_OF_SCOPE = """
ration salary loan loans police theft divorce passport aadhaar visa insurance election vote voter job
fare fares ticket tickets driver drivers conductor cinema library driving transport
""".split()

# Advertising / spam vocabulary.
SPAM = """
buy sale discount offer offers click subscribe winner lottery casino prize coupon promo cheap earn followers
""".split()
