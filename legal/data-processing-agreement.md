# SMN — Data Processing Agreement (DPA)

**Effective Date:** 19 April 2026
**Last Updated:** 19 April 2026

> **IMPORTANT:** This document is a template. Have it reviewed by qualified legal
> counsel before publication.

This Data Processing Agreement ("DPA") supplements the Terms of Service between
Ley Labs Ltd ("Processor" / "SMN") and the entity agreeing to the Terms
("Controller" / "Customer") and governs the processing of personal data by
SMN on behalf of Customer.

---

## 1. Definitions

Terms not defined here have the meaning given in the Terms of Service. Additional
definitions:

- **"Personal Data"** — Any information relating to an identified or identifiable
  natural person, as defined by Applicable Data Protection Laws.
- **"Applicable Data Protection Laws"** — GDPR, UK GDPR, CCPA/CPRA, and any other
  applicable data protection legislation.
- **"Sub-processor"** — A third party engaged by SMN to process Personal Data on
  behalf of Customer.
- **"Data Breach"** — A breach of security leading to accidental or unlawful
  destruction, loss, alteration, unauthorised disclosure of, or access to,
  Personal Data.
- **"SCCs"** — The Standard Contractual Clauses for international data transfers
  adopted by the European Commission (Decision 2021/914).
- **"Technical and Organisational Measures" (TOMs)** — Security measures implemented
  to protect Personal Data, as described in Annex II.

---

## 2. Scope and Roles

2.1. **Customer as Controller.** Customer determines the purposes and means of
processing Personal Data submitted to the Service. Customer is the Controller
(or, where applicable, a Processor acting on behalf of its own controller).

2.2. **SMN as Processor.** SMN processes Personal Data solely on behalf of
Customer and in accordance with Customer's documented instructions as set out in
this DPA and the Terms of Service.

2.3. **Processing Details.** The subject matter, duration, nature, and purpose of
processing, and the categories of data subjects and Personal Data are described
in **Annex I**.

---

## 3. Customer Obligations

3.1. Customer warrants that it has all necessary rights and consents to provide
Personal Data to SMN and to authorise SMN's processing as described in this DPA.

3.2. Customer is responsible for ensuring that the use of the Service complies
with Applicable Data Protection Laws, including any requirements for data
protection impact assessments (DPIAs).

3.3. Customer shall configure appropriate policies, guardrails, and access
controls within the Service to protect Personal Data in accordance with its own
obligations.

---

## 4. SMN Obligations

4.1. **Instructions.** SMN shall process Personal Data only on documented
instructions from Customer, unless required by applicable law. If SMN believes
an instruction infringes Applicable Data Protection Laws, it will notify Customer
promptly.

4.2. **Confidentiality.** SMN ensures that persons authorised to process Personal
Data are bound by appropriate confidentiality obligations.

4.3. **Security.** SMN implements the Technical and Organisational Measures
described in **Annex II** to protect Personal Data.

4.4. **No Training.** SMN does NOT use Personal Data or Customer Data to train
machine learning or AI models.

4.5. **Assistance.** SMN will assist Customer in:
- Responding to data subject rights requests (access, erasure, portability, etc.)
- Conducting data protection impact assessments, where required
- Notifying supervisory authorities and data subjects of Data Breaches
- Demonstrating compliance with Applicable Data Protection Laws

---

## 5. Sub-processors

5.1. Customer provides general authorisation for SMN to engage Sub-processors,
subject to the requirements in this Section.

5.2. SMN maintains a list of current Sub-processors at https://leylabs.dev/legal/sub-processors,
which includes:

| Sub-processor | Purpose | Location |
|---------------|---------|----------|
| Amazon Web Services (AWS) | Cloud infrastructure | US / EU (customer choice) |
| Microsoft Azure | Cloud infrastructure | US / EU (customer choice) |
| Google Cloud Platform (GCP) | Cloud infrastructure | US / EU (customer choice) |
| Stripe, Inc. | Payment processing | US |

5.3. SMN will notify Customer at least 30 days before engaging a new
Sub-processor. Customer may object within that period by providing written notice
with reasonable grounds. If the objection cannot be resolved, Customer may
terminate the affected Services.

5.4. SMN imposes data protection obligations on Sub-processors no less protective
than those in this DPA.

---

## 6. Data Breach Notification

6.1. SMN will notify Customer of a Data Breach without undue delay and in any
event within 48 hours of becoming aware.

6.2. The notification will include:
- Description of the nature of the breach
- Categories and approximate number of data subjects affected
- Likely consequences
- Measures taken or proposed to mitigate

6.3. SMN will cooperate with Customer and take reasonable steps to mitigate the
effects of the breach.

---

## 7. Data Subject Rights

7.1. SMN will assist Customer in responding to data subject requests by:
- Providing self-service tools in the Service for data access and deletion
- Responding to written requests from Customer within 10 business days
- Not responding directly to data subjects unless directed by Customer

---

## 8. International Data Transfers

8.1. Where Personal Data is transferred from the EU/EEA/UK to a country without
an adequacy decision, the transfer is governed by the SCCs (Commission Decision
2021/914), which are incorporated by reference.

8.2. For transfers subject to the SCCs:
- Module Two (Controller to Processor) applies
- Annex I, II, and III of this DPA serve as the annexes to the SCCs
- The competent supervisory authority is the UK Information Commissioner's Office (ICO)
- The governing law is the laws of England and Wales

8.3. For UK transfers, the UK Addendum to the SCCs (as issued by the ICO) applies.

8.4. SMN will not transfer Personal Data to any country unless appropriate
safeguards are in place as required by Applicable Data Protection Laws.

---

## 9. Audits

9.1. SMN will make available to Customer all information necessary to demonstrate
compliance with this DPA.

9.2. Customer may conduct an audit (or appoint an independent auditor) once per
year with 30 days' written notice, during business hours, subject to reasonable
confidentiality obligations.

9.3. SMN may satisfy audit requests by providing:
- SOC 2 Type II report (when available)
- Penetration test results
- Responses to Customer's security questionnaire
- Access to relevant documentation

---

## 10. Data Deletion and Return

10.1. Upon termination of the agreement or written request, SMN will:
- Delete all Personal Data within 30 days, OR
- Return Personal Data in a standard format (JSON export), at Customer's election

10.2. SMN may retain Personal Data where required by applicable law, subject to
continued confidentiality and security obligations.

10.3. SMN will certify deletion in writing upon Customer's request.

---

## 11. Term

11.1. This DPA remains in effect for the duration of SMN's processing of Personal
Data on behalf of Customer.

11.2. Obligations regarding confidentiality, data deletion, and security survive
termination.

---

## Annex I — Details of Processing

| Element | Description |
|---------|-------------|
| **Subject matter** | Processing Personal Data as part of the SMN AI agent orchestration platform |
| **Duration** | For the term of the Customer's use of the Service |
| **Nature and purpose** | Storage, retrieval, task execution, audit logging, and analytics as instructed by Customer through the Service |
| **Categories of data subjects** | Customer's employees, end users, and any individuals whose data Customer submits |
| **Categories of Personal Data** | Names, email addresses, identifiers, and any Personal Data contained in task inputs/outputs or agent memory |
| **Sensitive data** | Only if Customer configures agents to process sensitive data. Customer bears responsibility for implementing appropriate safeguards (Article 9 GDPR) |

---

## Annex II — Technical and Organisational Measures

### Encryption
- Data in transit: TLS 1.2+ (TLS 1.3 preferred) for all connections
- Data at rest: AES-256 encryption for database and backup storage
- API keys stored as cryptographic hashes (SHA-256 + salt)

### Access Control
- API key authentication with tenant-scoped isolation
- Attribute-based access control (ABAC) policy engine
- Principle of least privilege for all system components
- Infrastructure access restricted to authorised personnel via MFA

### Monitoring and Logging
- Immutable audit trail for all data operations
- Security event monitoring with real-time alerting
- 90-day log retention (configurable)

### Data Isolation
- Multi-tenant architecture with strict tenant-scoped queries
- Network isolation via VPC/VNET with private subnets
- Security groups / NSGs with least-privilege rules

### Availability
- Multi-AZ / Zone-redundant deployment for production
- Automated database backups with point-in-time recovery
- Disaster recovery procedures documented and tested quarterly

### Incident Response
- 48-hour breach notification commitment
- Security incident response plan documented in SECURITY.md
- Regular security assessments and penetration testing

### Personnel
- Background checks for employees with access to production systems
- Data protection training for all staff
- Confidentiality agreements for all personnel

### Application Security
- Secure development lifecycle (CI/CD with SAST scanning)
- Input validation and parameterised database queries
- Runtime guardrails and content filtering
- Emergency kill switch for agent execution

---

## Annex III — List of Sub-processors

See Section 5.2 and https://leylabs.dev/legal/sub-processors for the current list.

---

**Signatures:**

**Customer (Controller):**
Name: _________________________
Title: _________________________
Date: _________________________
Signature: _________________________

**SMN (Processor):**
Name: _________________________
Title: _________________________
Date: _________________________
Signature: _________________________

---

*© 2026 Ley Labs Ltd. All rights reserved.*
