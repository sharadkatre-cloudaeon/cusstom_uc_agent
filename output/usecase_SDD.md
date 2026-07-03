# Use-Case Requirements (SDD)

## 1 · Use Case Snapshot
- **In a sentence or two, what do you want this to do?**
  I want to develop an HR Assistant Bot
- **What problem does it solve, and how is that handled today?**
  It will automate the process for the Employee Queries. Currently employees need to visit/call HR to clarify their queries
- **Who is the accountable owner for this?**
  HR

## 2 · Users & Impact
- **Who will use it, roughly how many, and how often?**
  By Company employyes, based on their queries they will use
- **Do its outputs materially affect individuals - eligibility, pricing, hiring, complaints, or anything customer-facing?**
  Not sure
- **Could it disadvantage or treat any group or region unfairly?**
  no

## 3 · What It Should Do
- **Walk me through what should happen start to finish - what kicks it off, what comes out?**
  There will be an chat bot, employee will ask the query e.g What is leave Policy, Chat Bot should look into the Company Knowledgrbase of HR polices and retrive the formated answer for employee using LLM/Agent
- **Should it only suggest or draft things for a person to action, or actually take actions and change things itself?**
  No action as of now
- **Does it follow fixed rules, or make judgement calls on messy, varied information?**
  Not sure
- **Is it a single task, or does it plan across several steps and systems and recover if something fails?**
  Single Task
- **Does it mainly create new content, move/process data, or analyse data to predict or recommend?**
  No new content is required. It should use whatever we have in knowledgebase

## 4 · Data
- **What information does it use, where does it live today, and how good is it?**
  Live and it is well maintained
- **Does any of it include personal, customer, or confidential data?**
  general company policies
- **Does it need your organisation's own documents or knowledge to answer correctly?**
  Yes

## 5 · Systems & Environment
- **Which systems does it connect to - and does it only read, or also change/write records?**
  Official company website
- **Will it share data with other departments or outside vendors?**
  no

## 6 · Trust, Oversight & Compliance
- **For any decision or action it takes, must a human approve first, or can it act on its own?**
  no
- **How important is it that users can see why or how it produced an answer?**
  not very much important
- **Are there laws, regulations, or company policies it must comply with?**
  no
- **Is there anything it must never do, or any topic or tone to avoid?**
  nothing

## 7 · Success, Scale & Constraints
- **What does 'good enough to ship' look like? How fast, how much volume, any deadlines or budget limits?**
  In two week time
- **If it's wrong or unavailable, is that a minor annoyance or a serious business/customer impact?**
  no
