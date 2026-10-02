"""Generate the labeled evaluation dataset for Phase 0 task 5.

Templates are written to read like real beneficiary submissions rather than
keyword lists: the whole point of the harness is to measure how a model does
on natural phrasing, so hand-written keyword probes would flatter every model.

Each category carries enough distinct templates (with paraphrases and varying
household circumstances) to produce a few hundred rows without repeating
identical sentences. Deterministic: no randomness, so the dataset is stable
across runs and the report is reproducible.

Run:  python eval/build_dataset.py
"""

import csv
from pathlib import Path

CATEGORIES = ["food", "housing", "medical", "education", "employment", "emergency"]

# (category, urgency_band) -> list of sentence templates.
# {n} is substituted with a household size to vary numeric context.
TEMPLATES: dict[str, list[str]] = {
    "food": [
        "Our family of {n} has run out of money for groceries and we cannot buy food for the week",
        "I need help with food, my wages were delayed and there is nothing in the fridge",
        "Please help us buy groceries, we have two children and no food until payday",
        "We are skipping meals because we cannot afford food this month",
        "A single mother with {n} children needs food assistance right now",
        "My elderly father has no food for the week and needs groceries",
        "We need financial help to buy food, we have nothing left to eat",
        "Our food supply has run out completely and we need emergency groceries",
        "I lost my job and cannot feed my family of {n}, we need food support",
        "Help us buy staple food items, we have had nothing to eat for two days",
        "We need a food bank referral, we have no money for groceries",
        "My child is going hungry and I need help buying food for my family",
        "Please provide food assistance, our household is completely without food",
        "I cannot afford groceries after rent took most of my income, need food help",
        "The food pantry helped last month but we need groceries again this month",
        "We need vouchers to buy food for {n} people including an infant",
        "My disability means I cannot work and I have no money for food",
        "There is no food in the house and we need help this week",
        "Our community kitchen needs food donations to feed families like mine",
        "I need to buy rice, beans and cooking oil, we have no groceries at home",
        "We are a family of {n} and need help putting food on the table this week",
        "My husband is ill and cannot work, we have no money for food",
        "I need food assistance, my benefits have not arrived this month",
        "There is nothing left in the cupboard and we need groceries today",
        "We need help feeding three children who have not eaten today",
        "Please help with groceries, we have used our last money on utilities",
        "I cannot provide meals for my family without help buying food",
        "We need support to buy enough food for the rest of the month",
        "A family we help has run out of food and needs an emergency grocery voucher",
        "I need food now, my wages have not come and my children are hungry",
        "Our household needs help buying food because both of us are unemployed",
        "Food assistance would help, we are choosing between heating and eating",
        "My family needs groceries and there is no one else who can help",
        "We have {n} people at home and not enough food for one more day",
    ],
    "housing": [
        "Our landlord gave us a notice and we are being evicted in two weeks",
        "We cannot pay rent this month and need help to stay in our home",
        "A family of {n} faces eviction and needs rent assistance urgently",
        "I am behind on rent and the landlord is threatening to lock us out",
        "We need help paying the rent or we will lose our apartment",
        "My rent is due and I have no money, I need housing support",
        "We are staying with relatives because we cannot afford our apartment",
        "I need emergency shelter, my family has nowhere to live this week",
        "Our house is being repossessed and we need help keeping a roof over our heads",
        "We need help with housing costs, rent is more than we can afford",
        "A single father with {n} children needs help paying rent before eviction",
        "I cannot keep up with mortgage payments and need housing assistance",
        "Our tenancy ended and we need temporary accommodation for the family",
        "We need rental assistance, the deposit for a new place is beyond us",
        "I am being evicted because I lost work and cannot pay the rent",
        "Please help us stay housed, we have an eviction date in three weeks",
        "We need help finding and paying for housing after a house fire",
        "My family needs a safe place to stay, we have no accommodation",
        "Rent is due and without help this month we will be on the street",
        "We need support to keep our home, the council has not helped",
        "A family of {n} needs emergency housing because we have nowhere to sleep",
        "I need help with rent after my hours were cut at work",
        "Our family is being evicted and we need housing support urgently",
        "We need help finding housing after being asked to leave our flat",
        "I cannot pay rent or the deposit for another place",
        "Our landlord has increased the rent beyond what we can manage",
        "We need help staying in our home while we look for work",
        "A young couple with {n} children need affordable housing assistance",
        "My family needs temporary accommodation while our house is repaired",
        "We have no rent money and need assistance to avoid eviction",
        "I need housing help because my building is being sold and we must leave",
        "Please help with rent, my hours were reduced and we are behind",
        "Our household needs help finding a safe and affordable home",
        "We need help to pay the rent in full or we must leave our apartment",
    ],
    "medical": [
        "I need help paying for hospital treatment, I cannot afford the cost",
        "My mother needs surgery and we have no money for the medical bills",
        "We need help with prescription medicine, the cost is too much for us",
        "A child in our family is seriously ill and needs medical treatment",
        "I am diabetic and cannot afford insulin and my medication this month",
        "Our family needs help with a hospital bill after an accident",
        "My father needs dialysis and we cannot pay for ongoing medical care",
        "I need financial help to pay for a clinic visit and tests",
        "Someone in our household was diagnosed with cancer and needs treatment money",
        "We need assistance covering medical costs, insurance does not cover this",
        "My son broke his arm playing and we cannot pay the hospital fees",
        "I need help buying medication for a chronic condition",
        "The clinic told us we must pay upfront and we have no funds",
        "A family member needs urgent surgery and we need help with costs",
        "We need help with medical expenses after a long illness",
        "My grandmother needs ongoing treatment and we cannot afford her care",
        "I need financial assistance for a medical procedure I cannot postpone",
        "Our child needs specialist medical care and the cost is overwhelming",
        "We need help paying for treatment after a diagnosis last month",
        "Prescription costs have gone up and I need help getting my medication",
        "A family of {n} needs help with medical bills after a hospital stay",
        "I need help paying for an operation that cannot wait",
        "My wife needs cancer treatment and we cannot pay for the care",
        "We need assistance with medical expenses, we have no insurance",
        "My child needs an operation and the cost is far beyond us",
        "I need help with the cost of seeing a specialist privately",
        "Our family needs help paying for a chronic illness treatment plan",
        "We need financial help for a hospital stay that has already happened",
        "My mother needs heart surgery and we need help with the costs",
        "I cannot afford the medication that keeps my condition under control",
        "A relative in our care needs hospital treatment we cannot fund",
        "We need help with the cost of an MRI scan and follow up care",
        "My family needs medical assistance for a long term condition",
        "Please help us pay for treatment, the bills are beyond what we can manage",
    ],
    "education": [
        "Our children need help with school fees, we cannot afford them",
        "I need financial help for books and uniforms for the new school term",
        "A student in our family is at risk of dropping out for lack of fees",
        "We need support to pay tuition for {n} children in school",
        "My child needs help with school supplies and exam fees",
        "The school asked for fees we do not have and the child is being sent home",
        "I need help paying for my education so I can finish my course",
        "Our family cannot afford the cost of school books this year",
        "A girl in our community needs help to stay in school past primary level",
        "I need financial assistance to pay for my children's schooling",
        "School fees are due and we have no money, help us keep the children in class",
        "My nephew needs support to pay for secondary school",
        "We need help with educational costs for children with special needs",
        "The cost of textbooks and uniforms has become unaffordable for us",
        "I need help to afford training and certification for a job",
        "Our son needs exam fees paid so he can take his final exams",
        "We cannot pay for school and the children are dropping out",
        "I want my daughter to stay in school but we have no money for fees",
        "Help us pay for the school term, food and fees are beyond us",
        "A family of {n} needs help keeping three children in school",
        "I need help with exam fees so my daughter can take her exams",
        "Our children need books and a bag before the term starts next week",
        "We cannot pay school fees and the head teacher has asked us to leave",
        "A young person needs help completing secondary education",
        "I need support to keep my children in school while I look for work",
        "The cost of school has risen and we need help with fees this year",
        "Our family needs financial help for our son's university place",
        "We need help with uniforms and transport for the children to attend school",
        "My child needs extra tutoring and we cannot afford it",
        "Please help us pay for school so the children are not sent home",
        "A student needs help with coursework costs and materials",
        "We need assistance with the school fees due next month",
        "I want to return to study but I cannot afford the course",
        "Our family needs help with the cost of school for the coming year",
    ],
    "employment": [
        "I lost my job and need help finding work to feed my family",
        "I need help preparing a CV and preparing for interviews",
        "Please help me find employment, I have been unemployed for months",
        "I need job placement support and help with interview preparation",
        "A single mother needs help getting a job and supporting her children",
        "I am looking for work but cannot attend interviews without transport help",
        "My family needs income and I need help finding a job quickly",
        "I need vocational training to qualify for work in my field",
        "We need help with job search because my company closed down",
        "I need help writing a resume and finding employment opportunities",
        "A young person in our family needs job placement and skills training",
        "I cannot feed my children and need work, please help me find a job",
        "I lost my income and need help starting a small business",
        "I need help to retrain because my industry has no more work",
        "Our family needs someone to help find employment after redundancy",
        "I am applying for jobs but need help with interview skills",
        "Please help me get work so I can provide for my household",
        "I need job support and guidance on applying for work",
        "A father needs work and childcare support to take a job",
        "I need livelihood support through employment rather than handouts",
        "A family of {n} needs help because the only earner was made redundant",
        "I need help finding part time work alongside my caring duties",
        "Please help me with job search skills, I have not worked in years",
        "We need income support through a job, not charity",
        "I need training and certification to get a better paying job",
        "My company closed and I need help finding new employment quickly",
        "A young man in our community needs job placement support",
        "I need help preparing for an interview I have next week",
        "Our household needs someone to help me access job opportunities",
        "I cannot find work after months of applying and need guidance",
        "We need help with transport to and from a job interview",
        "A woman needs childcare support so she can return to employment",
        "I need a job to feed my family of {n} and cannot find one",
        "Please help me get back into work after a long illness",
    ],
    "emergency": [
        "Our home caught fire and the family needs emergency shelter tonight",
        "There was a flood and we lost everything, we need emergency relief",
        "We need immediate help, a disaster destroyed our home",
        "A sudden medical emergency has left us needing urgent assistance now",
        "Our house burned down and we need emergency accommodation immediately",
        "A storm destroyed our home and we need urgent help to recover",
        "We need emergency support, there is a fire at our property right now",
        "The flood destroyed our belongings and we need help urgently",
        "Our family evacuated in a disaster and needs emergency assistance now",
        "We need critical help immediately, we have nowhere to stay tonight",
        "An earthquake damaged our home and we need emergency relief",
        "We need urgent food and shelter after a fire in our building",
        "Our home is uninhabitable after a disaster and we need help right away",
        "We need emergency funds to recover from a fire that destroyed everything",
        "A wildfire evacuation has left us with nothing and we need urgent help",
        "We need emergency assistance for our family, please respond quickly",
        "Our home collapsed in the storm and we need shelter urgently",
        "We need immediate relief after a disaster destroyed our belongings",
        "There is an emergency at our home and we need help right now",
        "We need critical assistance now, a fire destroyed our only possessions",
        "A family of {n} needs urgent help after their home was destroyed",
        "We need immediate assistance, there is nowhere safe for us to stay",
        "Our building is flooding and we need emergency help tonight",
        "I need urgent support, a gas leak made our home unsafe",
        "We lost everything in a fire and need help to recover quickly",
        "Please help us urgently, a disaster has ruined our lives this week",
        "Our family needs emergency relief after a sudden accident at home",
        "We need help immediately, we have no food and no shelter",
        "An emergency has left us without a home and we need assistance now",
        "We need critical help, our home is damaged beyond repair",
        "Our house is on fire and we need assistance immediately",
        "A storm has ruined our home and we need urgent financial help",
        "We need emergency support to get our family somewhere safe tonight",
        "The flood has taken everything and we need help right away",
    ],
}


def build_rows() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    sizes = [2, 3, 4, 5, 6]
    for category, templates in TEMPLATES.items():
        for index, template in enumerate(templates):
            size = sizes[index % len(sizes)]
            rows.append((template.format(n=size), category))
    return rows


def main() -> None:
    rows = build_rows()
    out_dir = Path(__file__).resolve().parent
    out_path = out_dir / "dataset.csv"

    # newline="" plus an explicit lineterminator keeps the committed file
    # LF-only on every platform; CI diffs it after regenerating.
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["text", "category"])
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for _, category in rows:
        counts[category] = counts.get(category, 0) + 1

    print(f"wrote {len(rows)} rows to {out_path}")
    for category in CATEGORIES:
        print(f"  {category:<12} {counts.get(category, 0)}")


if __name__ == "__main__":
    main()
