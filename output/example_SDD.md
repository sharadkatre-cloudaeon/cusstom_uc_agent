# Use-Case Requirements (SDD)

## 1 · Use Case Snapshot
- **In a sentence or two, what do you want this to do?**
  A tool that answers customer policy questions from our internal documents
- **What problem does it solve, and how is that handled today?**
  Customers email us and agents look it up manually; slow
- **Who is the accountable owner for this?**
  The customer service lead, Priya

## 2 · Users & Impact
- **Who will use it, roughly how many, and how often?**
  About 40 agents, many times a day
- **Do its outputs materially affect individuals - eligibility, pricing, hiring, complaints, or anything customer-facing?**
  Yes, it answers customers about orders and refunds
- **Could it disadvantage or treat any group or region unfairly?**
  It could if the documents favour certain regions

## 3 · What It Should Do
- **Walk me through what should happen start to finish - what kicks it off, what comes out?**
  Customer asks a question, it finds the answer in our docs and replies
- **Should it only suggest or draft things for a person to action, or actually take actions and change things itself?**
  It should suggest a draft for the agent to review
- **Does it follow fixed rules, or make judgement calls on messy, varied information?**
  It makes judgement calls on varied questions
- **Is it a single task, or does it plan across several steps and systems and recover if something fails?**
  Single task, just answer the question
- **Does it mainly create new content, move/process data, or analyse data to predict or recommend?**
  It creates a written answer

## 4 · Data
- **What information does it use, where does it live today, and how good is it?**
  Our policy PDFs and order data, fairly current
- **Does any of it include personal, customer, or confidential data?**
  Yes, customer names and order details
- **Does it need your organisation's own documents or knowledge to answer correctly?**
  Yes it needs our own policy documents

## 5 · Systems & Environment
- **Which systems does it connect to - and does it only read, or also change/write records?**
  It reads from the order system, read only
- **Will it share data with other departments or outside vendors?**
  No external sharing

## 6 · Trust, Oversight & Compliance
- **For any decision or action it takes, must a human approve first, or can it act on its own?**
  A human agent approves before sending
- **How important is it that users can see why or how it produced an answer?**
  Helpful for users to see the source
- **Are there laws, regulations, or company policies it must comply with?**
  GDPR applies, it's customer data
- **Is there anything it must never do, or any topic or tone to avoid?**
  It must never make up policy or give legal advice

## 7 · Success, Scale & Constraints
- **What does 'good enough to ship' look like? How fast, how much volume, any deadlines or budget limits?**
  Accurate, respond in a few seconds, handle busy periods
- **If it's wrong or unavailable, is that a minor annoyance or a serious business/customer impact?**
  Serious - wrong answers hurt customers
