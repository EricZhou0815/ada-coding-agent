# AI-Powered Automated Code Review Prompt

This document contains a structured prompt template for conducting comprehensive automated architecture and code reviews using AI assistants.

---

## How to Use This Prompt

1. **Copy the full prompt** from the "Master Prompt Template" section below
2. **Customize the context** section with your project specifics
3. **Paste into your AI assistant** (GitHub Copilot, ChatGPT, Claude, etc.)
4. **Review the generated report** and validate findings
5. **Track remediation** using the prioritized action items

---

## Master Prompt Template

```markdown
# Comprehensive Project Architecture & Code Review

You are an expert software architect and security auditor conducting a thorough review of a production codebase. Your goal is to provide actionable insights on architecture, design patterns, scalability, security, and code quality.

## Project Context

**Project Name:** [Your Project Name]
**Technology Stack:** [e.g., Python, FastAPI, React, PostgreSQL, Docker, AWS]
**Current Stage:** [e.g., MVP, Beta, Production]
**Team Size:** [e.g., 2-5 developers]
**Expected Scale:** [e.g., 1K users/month, 10K requests/day]

## Review Scope

Conduct a comprehensive analysis covering:

1. **Architecture Review**
   - System design and component separation
   - Distributed systems patterns (if applicable)
   - Data flow and state management
   - API design and versioning
   - Integration points and external dependencies

2. **Design Patterns Analysis**
   - Identify design patterns used (Factory, Strategy, Observer, etc.)
   - Detect anti-patterns (God Objects, tight coupling, code smells)
   - Evaluate SOLID principles adherence
   - Assess code reusability and modularity

3. **Scalability Assessment**
   - Current capacity limits (throughput, concurrency, storage)
   - Bottleneck identification (database, API, workers, external services)
   - Horizontal vs vertical scaling readiness
   - Resource utilization and efficiency
   - Growth roadmap (10x, 100x, 1000x scenarios)

4. **Security Audit**
   - Authentication and authorization mechanisms
   - Input validation and injection vulnerabilities
   - Secret management and credential handling
   - Rate limiting and DDoS protection
   - OWASP Top 10 compliance
   - Dependency vulnerabilities

5. **Code Quality**
   - Test coverage and testing strategy
   - Error handling and resilience
   - Logging and observability
   - Documentation completeness
   - Technical debt inventory

6. **Performance & Reliability**
   - Response time and latency analysis
   - Database query optimization
   - Caching strategy
   - Circuit breakers and retry logic
   - Monitoring and alerting setup

## Analysis Instructions

### Step 1: Reconnaissance
- Read the main README and architecture documentation
- Examine project structure and directory organization
- Review configuration files (docker-compose.yml, package.json, requirements.txt)
- Identify key components and their responsibilities

### Step 2: Deep Dive Analysis
For each component:
- Read core implementation files
- Trace data flow and dependencies
- Identify external service integrations
- Document assumptions and constraints

### Step 3: Security Scan
Search for:
- `subprocess.run`, `os.system`, `eval()` - Command injection risks
- API endpoints without authentication decorators
- Database queries with string interpolation - SQL injection
- Hardcoded secrets or credentials
- Missing input validation
- CORS misconfigurations

### Step 4: Pattern Recognition
Identify:
- Design patterns (positive)
- Anti-patterns (negative)
- Code duplication
- Tight coupling between modules
- Single Responsibility violations

### Step 5: Scalability Modeling
Calculate:
- Current capacity (requests/sec, concurrent users, data volume)
- Bottlenecks (CPU, memory, I/O, network, external APIs)
- Resource costs at 10x, 100x, 1000x scale
- Required infrastructure changes for growth

## Output Format

Generate a comprehensive report with the following structure:

### 1. Executive Summary (1 page)
- Overall grade (A-F) with brief justification
- Top 3 critical findings
- Top 3 strengths
- Recommended immediate actions
- Go/No-Go recommendation for production deployment

### 2. Architecture Assessment
- System diagram (text-based is fine)
- Component breakdown with ratings (1-5 stars)
- Strengths and weaknesses
- Comparison to industry best practices

### 3. Critical Issues (P0 - Block Launch)
For each critical issue:
- **Title:** Clear, concise description
- **Severity:** CRITICAL/HIGH/MEDIUM/LOW
- **Location:** File path and line numbers
- **Risk:** What can go wrong
- **Impact:** Business/technical consequences
- **Fix:** Concrete code example or solution
- **Effort:** Estimated hours to fix
- **Status:** ❌ Not Implemented / ⚠️ Partial / ✅ Implemented

### 4. High Priority Issues (P1 - Fix Soon)
Same format as P0, but less urgent

### 5. Design Pattern Analysis
- Patterns identified (with locations)
- Anti-patterns found (with refactoring suggestions)
- SOLID principles assessment (per principle)

### 6. Scalability Roadmap
Table format:
| Current | 10x | 100x | 1000x |
|---------|-----|------|-------|
| Infrastructure | | | |
| Cost/month | | | |
| Changes needed | | | |

### 7. Security Audit Results
- Vulnerabilities by severity (table)
- OWASP Top 10 checklist
- Security hardening recommendations

### 8. Technical Debt Registry
Table format:
| Item | Location | Impact | Effort | Priority |
|------|----------|--------|--------|----------|

### 9. Testing & Quality Metrics
- Test coverage percentage
- Testing gaps (unit, integration, e2e)
- Code quality metrics (if available)

### 10. Prioritized Action Plan
Week-by-week breakdown:
- **Week 1:** P0 items (with effort estimates)
- **Week 2:** P1 items
- **Week 3:** Testing & tuning
- **Week 4:** Documentation & launch prep

### 11. Cost Analysis
- Current monthly cost
- Projected costs at scale
- Optimization opportunities

### 12. Recommendations
- Short-term (0-3 months)
- Medium-term (3-6 months)
- Long-term (6-12 months)

## Evaluation Criteria

### Architecture (Weight: 25%)
- [ ] Clear separation of concerns
- [ ] Appropriate use of layers/tiers
- [ ] Loose coupling, high cohesion
- [ ] Scalable design
- [ ] Resilient to failures

### Security (Weight: 30%)
- [ ] Authentication implemented
- [ ] Authorization granular and correct
- [ ] Input validation comprehensive
- [ ] Secrets managed securely
- [ ] Dependencies up-to-date
- [ ] No critical vulnerabilities

### Code Quality (Weight: 20%)
- [ ] Test coverage >70%
- [ ] Clear, readable code
- [ ] Proper error handling
- [ ] Comprehensive logging
- [ ] Documentation complete

### Performance (Weight: 15%)
- [ ] Meets latency requirements
- [ ] Efficient resource usage
- [ ] Proper caching strategy
- [ ] Database queries optimized

### Maintainability (Weight: 10%)
- [ ] Low technical debt
- [ ] Good design patterns
- [ ] Easy to extend
- [ ] Clear code organization

## Grading Scale

**A (90-100%):** Production-ready, industry best practices, minor improvements only
**B (80-89%):** Solid foundation, some gaps, ready after fixes
**C (70-79%):** Functional but significant issues, major refactoring needed
**D (60-69%):** Multiple critical problems, not ready for production
**F (<60%):** Fundamental flaws, requires redesign

## Special Focus Areas

Depending on project type, emphasize:

**For Web APIs:**
- Rate limiting and DDoS protection
- API versioning strategy
- Request/response validation
- Authentication mechanisms

**For Data-Intensive Apps:**
- Database indexing strategy
- Query optimization
- Data migration approach
- Backup and recovery

**For Microservices:**
- Service boundaries and contracts
- Inter-service communication
- Distributed tracing
- Service mesh considerations

**For AI/ML Systems:**
- Model versioning and deployment
- A/B testing infrastructure
- Feature store design
- Model monitoring and drift detection

## Output Deliverables

1. **Markdown Report:** `docs/review_report_[DATE].md`
2. **Issue Tracker:** Create GitHub issues for P0/P1 items (optional)
3. **Metrics Dashboard:** If tooling available
4. **Executive Presentation:** 5-slide summary for stakeholders

## Follow-Up Actions

After generating the report:

1. **Validate Findings:** Manually verify top 5 critical issues
2. **Estimate Effort:** Review time estimates with development team
3. **Prioritize:** Adjust priorities based on business context
4. **Create Tickets:** Convert action items to tracked work items
5. **Schedule Review:** Set date for follow-up review (e.g., 30 days)

## Example Queries to Run

Use these specific searches to accelerate the review:

```python
# Security scans
grep -r "shell=True" .
grep -r "eval(" .
grep -r "PASSWORD" . | grep -v ".git"
grep -r "@app.post" . | grep -v "Depends"

# Pattern detection
grep -r "class.*Manager" .
grep -r "def __init__" . | wc -l

# Complexity analysis
find . -name "*.py" -exec wc -l {} \; | sort -rn | head -20

# Dependency audit
pip list --outdated
npm audit
```

## Quality Checklist

Before finalizing the report, ensure:

- [ ] All critical findings have concrete examples (file + line)
- [ ] Every recommendation includes implementation guidance
- [ ] Effort estimates are realistic (conservative)
- [ ] Priorities align with business goals
- [ ] Code examples are syntactically correct
- [ ] Links to documentation are valid
- [ ] Severity ratings are justified
- [ ] Action plan is achievable
- [ ] Executive summary fits on one page
- [ ] Report is formatted consistently

===========================================
END OF TEMPLATE - BEGIN YOUR REVIEW BELOW
===========================================

Now, analyze the codebase and generate a comprehensive review report following the structure above.
```

---

## Customization Guide

### For Different Project Types

**Backend API Project:**
```markdown
Additional focus areas:
- API endpoint security and validation
- Database connection pooling and query performance
- Rate limiting and throttling
- Webhook signature verification
- Background job processing reliability
```

**Frontend Application:**
```markdown
Additional focus areas:
- State management architecture
- Component reusability and design system
- Bundle size and performance optimization
- Accessibility (WCAG compliance)
- Cross-browser compatibility
```

**Data Pipeline:**
```markdown
Additional focus areas:
- Data quality and validation
- Idempotency and exactly-once processing
- Backpressure and flow control
- Dead letter queue handling
- Data lineage and observability
```

**Mobile Application:**
```markdown
Additional focus areas:
- Offline-first architecture
- Battery and memory efficiency
- Network resilience
- App size and startup time
- Platform-specific best practices
```

### Adjusting Severity Thresholds

**Early Stage Startup (MVP):**
- P0: Blocks user adoption or causes data loss
- P1: Causes occasional failures or bad UX
- P2: Technical debt, refactoring opportunities

**Enterprise Production:**
- P0: Security vulnerabilities, compliance violations, data breaches
- P1: Performance degradation, reliability issues
- P2: Maintainability concerns, missing monitoring

### Review Frequency Recommendations

| Stage | Frequency | Scope |
|-------|-----------|-------|
| **MVP Development** | Every major milestone | Full review |
| **Pre-Launch** | Weekly | Security + critical path |
| **Beta** | Bi-weekly | Performance + security |
| **Production** | Monthly | Full review |
| **Mature** | Quarterly | Strategic review |

---

## Integration with CI/CD

### Automated Daily Scans

Create `.github/workflows/ai-review.yml`:

```yaml
name: AI Architecture Review

on:
  schedule:
    - cron: '0 9 * * 1'  # Every Monday at 9 AM
  workflow_dispatch:

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Run AI Review
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          # Use AI API to analyze codebase
          # Send prompt from this template
          # Generate report
          
      - name: Create Issue if Critical Findings
        if: contains(steps.review.outputs.severity, 'CRITICAL')
        uses: actions/github-script@v6
        with:
          script: |
            github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: '🚨 Critical Security Issues Found in AI Review',
              body: '${{ steps.review.outputs.summary }}'
            })
```

### Pre-Commit Hook

Create `.git/hooks/pre-push`:

```bash
#!/bin/bash

echo "Running quick AI security scan..."

# Run focused security checks before push
# Scan for common vulnerabilities
# Block push if critical issues found

exit 0
```

---

## Best Practices

### Do's ✅
- Run review at consistent intervals
- Focus on actionable insights, not just problems
- Provide concrete code examples
- Estimate effort realistically
- Track remediation progress
- Update review criteria as project evolves

### Don'ts ❌
- Don't review too frequently (review fatigue)
- Don't ignore context (business constraints)
- Don't provide vague recommendations
- Don't underestimate security issues
- Don't skip validation of AI findings
- Don't forget to celebrate improvements

---

## Metrics to Track Over Time

Create a dashboard tracking:

```
Review Metrics:
- Overall Grade Trend (A-F over time)
- Critical Issues Count
- Mean Time to Remediate (by priority)
- Technical Debt Ratio
- Test Coverage %
- Security Score (0-100)
- Code Quality Score (0-100)
- Architecture Health Score (0-100)
```

---

## Example Usage

**Step 1:** Customize the prompt
```markdown
**Project Name:** Ada AI Coding Agent
**Technology Stack:** Python, FastAPI, PostgreSQL, Redis, Celery, Docker
**Current Stage:** MVP → Beta
**Team Size:** 2 developers
**Expected Scale:** 10K jobs/month
```

**Step 2:** Paste into AI assistant

**Step 3:** Review generated report at `docs/review_report_2026-03-03.md`

**Step 4:** Create GitHub issues for P0 items
```bash
gh issue create --title "P0: Add API Authentication" \
  --body "See review report section 3.1" \
  --label security,p0
```

**Step 5:** Track progress, re-run in 30 days

---

## Advanced Techniques

### Differential Review

Compare two commits or branches:

```markdown
# Modified Prompt Addition

**Review Type:** Differential Analysis

**Base Version:** main branch (commit abc123)
**Target Version:** feature/new-api (commit def456)

Focus on:
- New security vulnerabilities introduced
- Performance regressions
- Breaking changes
- New technical debt

Output format: Only report on changes, not entire codebase.
```

### Focused Deep Dive

Target specific areas:

```markdown
# Modified Prompt Addition

**Review Scope:** NARROW - Authentication System Only

Files to analyze:
- api/auth.py
- middleware/auth_middleware.py
- tests/test_auth.py

Depth: MAXIMUM - Include security analysis, threat modeling, and compliance checks.
```

### Compliance Audit

For regulated industries:

```markdown
# Modified Prompt Addition

**Compliance Requirements:**
- GDPR (data privacy)
- SOC 2 Type II (security controls)
- HIPAA (healthcare data)
- PCI DSS (payment data)

Additional checks:
- Data retention policies
- Audit logging completeness
- Encryption at rest and in transit
- Access control documentation
```

---

## Tools & Resources

**Static Analysis Tools to Combine:**
- **Bandit** (Python security) - `bandit -r .`
- **Semgrep** (pattern matching) - `semgrep --config=auto`
- **SonarQube** (code quality) - Full platform
- **Trivy** (dependency scanning) - `trivy fs .`
- **OWASP Dependency Check** - Vulnerability scanner

**AI Models Recommended:**
- GPT-4 (best for architecture)
- Claude 3 Opus (best for code review)
- GitHub Copilot (integrated in IDE)
- Amazon CodeGuru (AWS-specific)

**Report Format Converters:**
```bash
# Convert Markdown to PDF
pandoc review_report.md -o review_report.pdf --pdf-engine=wkhtmltopdf

# Convert to HTML
pandoc review_report.md -o review_report.html -s --css=style.css

# Convert to Confluence/Notion (copy paste HTML)
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-03 | Initial template based on Ada project review |
| 1.1 | TBD | Add ML/AI specific review criteria |
| 2.0 | TBD | Integration with automated scanning tools |

---

**Maintained by:** Engineering Team  
**Last Updated:** March 3, 2026  
**Next Review:** Quarterly (June 2026)
