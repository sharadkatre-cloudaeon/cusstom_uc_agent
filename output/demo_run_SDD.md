# Use-Case Requirements (SDD)

## 1 · Use Case Snapshot
- **In a sentence or two, what do you want this to do?**
  I want a tool that analyzes sales data and predicts next quarter revenue trends.
- **What problem does it solve, and how is that handled today?**
  We handle forecasting manually in spreadsheets today.
- **Who is the accountable owner for this?**
  Jane Smith, Head of Sales Analytics

## 2 · Users & Impact
- **Who will use it, roughly how many, and how often?**
  About 15 sales managers, weekly
- **Do its outputs materially affect individuals - eligibility, pricing, hiring, complaints, or anything customer-facing?**
  No, it only affects internal planning reports
- **Could it disadvantage or treat any group or region unfairly?**
  No fairness concerns

## 3 · What It Should Do
- **Walk me through what should happen start to finish - what kicks it off, what comes out?**
  It should read our CRM export and produce a forecast dashboard
- **Should it only suggest or draft things for a person to action, or actually take actions and change things itself?**
  It suggests actions but a human approves before anything changes
- **Does it follow fixed rules, or make judgement calls on messy, varied information?**
  Mostly rules-based calculations with some trend analysis
- **Is it a single task, or does it plan across several steps and systems and recover if something fails?**
  Single step - upload file, get report
- **Does it mainly create new content, move/process data, or analyse data to predict or recommend?**
  It analyzes data and predicts outcomes

## 4 · Data
- **What information does it use, where does it live today, and how good is it?**
  No external sharing
- **Does any of it include personal, customer, or confidential data?**
  A human reviews every forecast before sharing
- **Does it need your organisation's own documents or knowledge to answer correctly?**
  We follow GDPR for customer data

## 5 · Systems & Environment
- **Which systems does it connect to - and does it only read, or also change/write records?**
  Yes, GDPR applies to customer personal data in deals
- **Will it share data with other departments or outside vendors?**
  We need audit logs of who ran forecasts

## 6 · Trust, Oversight & Compliance
- **For any decision or action it takes, must a human approve first, or can it act on its own?**
  Historical deal data from CRM
- **How important is it that users can see why or how it produced an answer?**
  Salesforce CSV exports, good quality
- **Are there laws, regulations, or company policies it must comply with?**
  Yes personal customer data included
- **Is there anything it must never do, or any topic or tone to avoid?**
  No internal knowledge base needed

## 7 · Success, Scale & Constraints
- **What does 'good enough to ship' look like? How fast, how much volume, any deadlines or budget limits?**
  Salesforce read only
- **If it's wrong or unavailable, is that a minor annoyance or a serious business/customer impact?**
  No sharing outside the team
