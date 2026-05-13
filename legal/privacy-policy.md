# SMN — Privacy Policy

**Effective Date:** 19 April 2026
**Last Updated:** 19 April 2026

> **IMPORTANT:** This document is a template. Have it reviewed by qualified legal
> counsel before publication.

---

## 1. Introduction

This Privacy Policy describes how Ley Labs Ltd ("SMN", "we", "us", or
"our") collects, uses, and protects personal data when you use the SMN platform,
APIs, website, and related services (the "Service").

We are committed to protecting your privacy and processing personal data in
compliance with the General Data Protection Regulation (GDPR), the California
Consumer Privacy Act (CCPA), and other applicable privacy laws.

---

## 2. Data Controller / Data Processor

- **When you create an account:** We act as the **data controller** for your
  account information.
- **When you process data through the Service:** We act as the **data processor**
  on your behalf. You are the data controller for Customer Data submitted to the
  platform, and our processing is governed by the Data Processing Agreement (DPA).

---

## 3. Information We Collect

### 3.1 Account Information
- Name, email address, organisation name
- Billing information (processed by Stripe — we do not store card numbers)
- API keys and authentication credentials (stored as cryptographic hashes)

### 3.2 Usage Data
- API request metadata (timestamps, endpoints, response codes)
- Task execution logs (task IDs, status, duration — not task content)
- Feature usage analytics (aggregated, non-identifying)
- IP addresses and user agent strings

### 3.3 Customer Data (Processed on Your Behalf)
- Agent configurations and policies
- Task inputs and outputs
- Memory entries and checkpoint data
- Audit trail entries

### 3.4 Information We Do NOT Collect
- We do **not** read, access, or analyse the content of your tasks or agent
  interactions except as necessary to provide the Service
- We do **not** use Customer Data to train AI/ML models
- We do **not** sell personal data to third parties
- We do **not** use tracking cookies for advertising

---

## 4. How We Use Information

| Purpose | Legal Basis (GDPR) | Data Categories |
|---------|-------------------|-----------------|
| Provide the Service | Contract performance | Account, Usage, Customer Data |
| Billing and invoicing | Contract performance | Account, Usage |
| Security monitoring and abuse prevention | Legitimate interest | Usage, IP addresses |
| Service improvement and debugging | Legitimate interest | Usage (aggregated) |
| Legal compliance | Legal obligation | As required |
| Customer support | Contract performance | Account, Usage |
| Service notifications | Contract performance | Account (email) |

---

## 5. Data Sharing

We share personal data only in the following circumstances:

### 5.1 Service Providers
We use the following categories of sub-processors:

| Provider | Purpose | Data Shared |
|----------|---------|-------------|
| Cloud infrastructure (AWS/Azure/GCP) | Hosting | Customer Data (encrypted) |
| Stripe | Payment processing | Billing data |
| LLM providers (customer-configured) | AI inference | Task content (via customer API keys) |
| Email service | Transactional emails | Email address |

A full list of sub-processors is available at https://leylabs.dev/legal/sub-processors.

### 5.2 Legal Requirements
We may disclose information when required by law, regulation, legal process, or
governmental request. We will notify you unless prohibited by law.

### 5.3 Business Transfers
In the event of a merger, acquisition, or asset sale, personal data may be
transferred. We will notify you before your data becomes subject to a different
privacy policy.

### 5.4 With Your Consent
We may share information with your explicit consent.

---

## 6. Data Retention

| Data Category | Retention Period | Basis |
|---------------|-----------------|-------|
| Account information | Duration of account + 30 days | Contract |
| Billing records | 7 years | Legal obligation (tax) |
| API request logs | 90 days | Legitimate interest |
| Audit trail | 1 year (configurable per tenant) | Contract |
| Customer Data | Duration of account + 30 days | Contract |
| Security logs | 1 year | Legitimate interest |

Upon account termination, we delete Customer Data within 30 days except where
retention is required by law.

---

## 7. Data Security

We implement comprehensive technical and organisational measures:

- **Encryption in transit:** TLS 1.2+ for all connections (TLS 1.3 preferred)
- **Encryption at rest:** AES-256 for database storage, encrypted backups
- **Access control:** Role-based access, API key authentication with scoping
- **Audit logging:** Immutable audit trail for all data operations
- **Infrastructure:** Private networking (VPC/VNET), least-privilege security groups
- **Application:** Input validation, parameterised queries, rate limiting, guardrails
- **Employee access:** Access to production data on need-to-know basis only
- **Incident response:** Security incident procedures defined in SECURITY.md

See our Security Policy (SECURITY.md) for full details.

---

## 8. Your Rights

### 8.1 Rights Under GDPR (EU/EEA/UK)
You have the right to:

- **Access** — Request a copy of your personal data
- **Rectification** — Correct inaccurate data
- **Erasure** — Request deletion ("right to be forgotten")
- **Restriction** — Limit how we process your data
- **Portability** — Receive your data in a structured format
- **Object** — Object to processing based on legitimate interest
- **Withdraw consent** — Where processing is based on consent

To exercise these rights, contact privacy@leylabs.dev. We will respond within 30 days.

You also have the right to lodge a complaint with your local Data Protection
Authority.

### 8.2 Rights Under CCPA (California)
California residents have the right to:

- **Know** what personal information we collect, use, and disclose
- **Delete** personal information we hold
- **Opt-out** of the "sale" of personal information (we do not sell data)
- **Non-discrimination** for exercising your rights

To exercise these rights, contact privacy@leylabs.dev or visit https://leylabs.dev/privacy-request.

We do not sell personal information. We do not use or disclose sensitive personal
information for purposes other than those permitted by the CCPA.

---

## 9. International Data Transfers

If your data is transferred outside the EU/EEA/UK, we ensure appropriate
safeguards:

- **Standard Contractual Clauses (SCCs):** Incorporated into our DPA
- **Adequacy decisions:** Where the destination country has an adequacy decision
- **Data residency:** Enterprise customers can specify deployment regions

---

## 10. Children's Privacy

The Service is not directed to individuals under 18. We do not knowingly collect
personal data from children. If we learn we have collected data from a child, we
will delete it promptly.

---

## 11. Cookies and Tracking

### Website (smn.dev)
We use only essential cookies required for the Service to function:

| Cookie | Purpose | Duration |
|--------|---------|----------|
| `session_id` | Authentication session | Session |
| `csrf_token` | Cross-site request forgery protection | Session |

We do **not** use advertising cookies, analytics trackers, or social media
pixels.

### API
The API does not use cookies. Authentication is via API key headers.

---

## 12. Changes to This Policy

We may update this Privacy Policy from time to time. We will notify you of
material changes via email or a prominent notice on the Service at least 30 days
before the effective date.

---

## 13. Contact Information

**Data Protection Officer:** Frederick Cameron Ley

- **Email:** privacy@leylabs.dev
- **Address:** Southampton, United Kingdom

For EU/EEA representative (if applicable):
- To be appointed when required by scale of EU data processing.

---

*© 2026 Ley Labs Ltd. All rights reserved.*
