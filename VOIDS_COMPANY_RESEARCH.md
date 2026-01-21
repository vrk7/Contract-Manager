# VOIDS Company Deep Dive - Know Your Audience

*Understanding the business helps you ask better questions and position your experience*

---

## Company Overview

**Name:** VOIDS
**Website:** https://www.voids.ai/
**Founded:** ~2023 (product launch June 2023)
**Location:** Hamburg, Germany (hybrid office in city center)
**Size:** Small/scaling (based on job posting tone)
**Stage:** Growth stage (300% growth past year, doubling ARR in 2025)

**Co-founders:**
- **Tobi (Tobias)** - CTO & Co-founder (your interviewer)
- **Jannik** - CEO & Co-founder
- Background: E-commerce growth + AI-based demand forecasting expertise

---

## What They Do - In Simple Terms

**Problem They Solve:**
D2C (direct-to-consumer) brands struggle with inventory management:
- Too much inventory → cash tied up, storage costs, waste
- Too little inventory → stockouts, lost sales, unhappy customers
- Manual forecasting → time-consuming, inaccurate, reactive

**Their Solution:**
AI-powered demand forecasting software that:
- Predicts product-level demand with high accuracy
- Identifies risks (stockouts, overstock) before they happen
- Recommends specific actions (order X units by Y date)
- Achieves 98% inventory efficiency in weeks

**Value Proposition:**
- **Speed:** 1/10 the time vs. traditional methods
- **ROI:** 20x return on investment
- **Cash impact:** Six-figure cash profits for customers
- **Efficiency:** 98% inventory efficiency (industry-leading)

---

## Target Customers

**Who:**
- D2C e-commerce brands (direct to consumer, not B2B wholesale)
- SMEs (small-medium enterprises)
- Specific verticals: Fashion, Sports, Consumer Goods

**Notable customers:**
- FC Bayern (football/soccer club merchandise)
- 6pm (footwear/fashion)
- Rosental (organics/lifestyle)
- Blackroll (fitness equipment)
- 50+ total success stories

**Customer profile:**
- $5M-$100M annual revenue (estimated)
- 100-10,000 SKUs (stock-keeping units)
- Selling through own website + marketplaces (Shopify, Amazon, etc.)
- Currently using spreadsheets or basic ERP tools

---

## The Technical Challenge - Forecasting for D2C

### Why D2C Forecasting is Hard

1. **Sparse data:**
   - New products have no sales history
   - Seasonal items sell only 3-4 months/year
   - Flash sales create unusual spikes

2. **External factors:**
   - Marketing campaigns change demand
   - Influencer posts cause sudden spikes
   - Competitors' actions affect sales
   - Weather, holidays, trends

3. **Supply chain complexity:**
   - Multiple suppliers with different lead times
   - Minimum order quantities
   - Shipping delays, customs

4. **SKU explosion:**
   - Variants (size, color) → 1 product = 20 SKUs
   - Cannibalization between similar products
   - Bundle/cross-sell effects

### What VOIDS Must Do

1. **Data ingestion:**
   - Connect to Shopify, WooCommerce, Amazon, etc.
   - Pull sales data, inventory levels, purchase orders
   - Handle different data formats/APIs

2. **Forecasting models:**
   - Time-series forecasting (ARIMA, Prophet, LSTM?)
   - Handle seasonality, trends, outliers
   - Confidence intervals (80% likely to sell 100-150 units)
   - New product forecasting (similar product patterns)

3. **Risk identification:**
   - Calculate days of inventory remaining
   - Compare to supplier lead times
   - Flag high-risk SKUs (stockout in <14 days)

4. **Action recommendations:**
   - "Order 500 units of SKU X by Feb 10 to avoid stockout"
   - "Reduce price on SKU Y - excess inventory detected"
   - Purchase order draft generation

5. **Dashboard/UX:**
   - Show 1000+ SKUs in digestible format
   - Filter by risk level, category, supplier
   - Charts: forecast vs. actual, inventory trends
   - Alerts: high-priority risks

---

## Technical Stack - What You'll Work With

### Current Stack

**Frontend:**
- Next.js 15 (React framework)
- TypeScript (type safety)
- TailwindCSS (utility-first CSS)
- shadcn/ui (component library based on Radix UI)

**Backend:**
- Next.js (fullstack - API routes)
- Migrating from NestJS (Node.js framework)
- TypeScript end-to-end

**Database:**
- PostgreSQL (relational database)
- Drizzle ORM (TypeScript-first ORM)

**Infrastructure:**
- Vercel (hosting, serverless functions)
- Likely AWS/GCP for heavy compute (model training)

**AI Tools:**
- GitHub Copilot (code completion)
- Cursor (AI-powered IDE)
- ChatGPT (debugging, research)
- v0.dev (UI generation from Vercel)

### Why They're Migrating NestJS → Next.js

**Speculation (good to ask about):**
- Reduced complexity (one framework for frontend + backend)
- Better Vercel integration (Next.js is Vercel's product)
- Server components (React Server Components in Next.js 15)
- Smaller team = simpler stack
- TypeScript end-to-end with shared types

---

## Engineering Culture - What They Value

**From job description:**

1. **Autonomy:**
   - "Decide yourself what to focus on—without bureaucracy"
   - "Lightweight consultation with CTO"
   - Engineers own features end-to-end

2. **Speed:**
   - "Ship daily"
   - 15-min daily standups
   - 30-min weekly planning
   - "Get things done"

3. **Pragmatism:**
   - "Optimize for speed versus long-term code maintainability"
   - Don't over-engineer
   - MVP → iterate based on customer feedback

4. **Customer focus:**
   - "Engage actively with customers"
   - "Build first relationships with customers"
   - Feedback drives roadmap

5. **AI-driven:**
   - "Actively leverage Copilot, GPT-4, and other AI tools"
   - Not afraid to use AI for productivity
   - Focus on outcomes, not typing code

**What this means for you:**
- They want someone who ships fast, not perfect code
- You'll talk to customers (not just build tickets)
- You'll make architectural decisions (not just implement)
- You'll use AI tools daily (they expect this)

---

## Growth Metrics - Why This Role Exists

**Traction:**
- Product launch: June 2023 (~1.5 years old)
- Growth: 300% year-over-year (4x in one year)
- Target: Double ARR by end of 2025 (2x in 12 months)
- Customers: 50+ success stories

**What this means:**
- Product-market fit achieved (300% growth)
- Scaling challenges ahead (need more engineers)
- You'll have significant impact (small team, high growth)
- Opportunity to shape the product (still early)

**Hiring this role because:**
- Too much customer demand, not enough engineering capacity
- Need to build features faster to stay ahead of competitors
- Technical debt from rapid growth (NestJS → Next.js migration)
- Want to improve platform scalability (current system likely straining)

---

## Competitive Landscape - Who They Compete With

**Likely competitors:**
1. **Legacy inventory systems:** SAP, Oracle, NetSuite (slow, expensive, not AI-driven)
2. **Spreadsheets:** Excel/Sheets (manual, error-prone, doesn't scale)
3. **Other AI forecasting tools:** Inventory Planner, Forecastly, etc.

**VOIDS's differentiation:**
- **Speed:** Results in weeks, not months
- **Accuracy:** 98% inventory efficiency (competitors likely 80-90%)
- **D2C focus:** Built for e-commerce brands, not generic manufacturing
- **Ease of use:** Simple UI vs. complex ERP interfaces

---

## Key Challenges They're Likely Facing (Good to Ask About)

### Technical Challenges

1. **Scaling forecasting models:**
   - Computing forecasts for 1000s of SKUs across 50+ customers
   - Model training time increasing
   - Need for distributed computing?

2. **Data integrations:**
   - Every customer uses different e-commerce platforms
   - APIs change, break integrations
   - Data quality issues (missing data, duplicates)

3. **Real-time updates:**
   - Customers want live inventory dashboards
   - Sales data changes constantly
   - How often to recompute forecasts?

4. **Model accuracy:**
   - New products hard to forecast (no history)
   - Sudden market changes (COVID-like events)
   - Seasonal products (limited training data)

5. **Dashboard performance:**
   - Loading 1000+ SKUs with charts is slow
   - Need for virtual scrolling, pagination, caching

### Product Challenges

1. **User adoption:**
   - Customers used to manual processes
   - Building trust in AI recommendations
   - Change management with their teams

2. **Feature prioritization:**
   - Which features drive retention vs. acquisition?
   - Balance between new features and scalability

3. **Customer feedback loop:**
   - How to gather feedback systematically?
   - Prioritizing feature requests from 50+ customers

---

## Questions You Should Ask (Copy from Cheat Sheet)

**About the migration:**
1. "You're migrating from NestJS to Next.js - what drove that decision? Was it primarily for Vercel integration, server components, or team simplicity?"

**About the forecasting challenge:**
2. "How do you handle forecasting for new products with no sales history? Do you use similar product patterns or category averages?"

3. "What's your model retraining cadence? Do you retrain daily, weekly, or event-driven when accuracy degrades?"

**About data:**
4. "How do you handle data quality issues - missing sales data, duplicate records, or integration outages?"

5. "What does your data pipeline look like from customer Shopify store to forecast generation?"

**About scale:**
6. "As you double ARR, what technical capabilities need to scale first? Is it model inference, data processing, or dashboard performance?"

**About product:**
7. "What's been the hardest data visualization challenge? How do you make complex forecasts actionable for non-technical users?"

8. "How do customers typically discover your highest-value features - through onboarding, support, or exploration?"

**About culture:**
9. "You ship daily with lightweight CTO consultation - how do you balance autonomy with architectural alignment?"

10. "What does a feature go from customer request to production? Walk me through a recent example."

---

## Your Positioning - Why You're a Great Fit

### 1. You Solve Similar Problems

| VOIDS Challenge | Your Experience |
|-----------------|-----------------|
| Complex data → simple UI | Contract analysis → risk scores |
| Multi-step data pipelines | Extract → retrieve → score → validate |
| Real-time processing | SSE streaming, sub-400ms voice latency |
| B2B trust requirements | Playbook versioning, audit trails |
| AI in production | Claude API, RAG, guardrails |

### 2. You Have the Tech Stack

| VOIDS Stack | Your Proficiency |
|-------------|------------------|
| TypeScript | ✅ Recently migrated, production use |
| React | ✅ Multiple projects, hooks, state management |
| PostgreSQL | ✅ Current project, async queries, indexes |
| Next.js | ⚠️ Strong React, fast learner |

### 3. You Share Their Values

| VOIDS Value | Your Proof |
|-------------|-----------|
| Ship fast | Contract analyzer deployed in weeks |
| Customer focus | Built SSE streaming for better UX |
| Ownership | End-to-end: design → deploy → maintain |
| Pragmatism | Heuristic fallback instead of perfect NER |
| AI-driven | Use Cursor, Claude Code daily |

---

## Potential Red Flags to Address Proactively

### Red Flag 1: "Too academic" (Sony, Harvard)
**Address it:** "My research experience taught me rigorous thinking, but I'm fundamentally a builder. I shipped production systems at Capgemini, Kontex, and my contract analyzer is live on AWS. I thrive in fast-paced, ship-daily environments."

### Red Flag 2: "Job hopping" (short stints)
**Address it:** "My recent roles were intentional: Sony was a 6-month internship to learn semantic search at scale. Kontex was a contract gig to optimize their RAG pipeline. I'm looking for a full-time role where I can have long-term impact - VOIDS's growth trajectory is exactly that opportunity."

### Red Flag 3: "Overqualified" (ML expertise for full-stack role)
**Address it:** "I don't want to be siloed in ML - I want to own features end-to-end. VOIDS is perfect because your forecasting challenges need both ML intuition and full-stack execution. I can understand the model outputs AND build the dashboard to visualize them."

---

## Final Prep - Before the Interview

1. **Browse their website:** https://www.voids.ai/
   - Look at case studies, testimonials
   - Understand their messaging
   - Note specific customer wins

2. **Review this document:** Internalize the business context

3. **Re-read job description:** Map your experience to each requirement

4. **Practice your opening:** 60-second intro (see cheat sheet)

5. **Prepare 3-4 questions:** Technical + product + culture mix

6. **Mental state:** Confident but curious, excited but professional

---

You've got this! You have the right experience, the right mindset, and the right enthusiasm. Show them you're ready to ship features, talk to customers, and help them double ARR. 🚀
