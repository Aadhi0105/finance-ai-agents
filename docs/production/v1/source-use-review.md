# Preliminary source-use permission review

Reviewed 10 October 2026. **Engineering evidence review, not legal approval.**
Public availability, a successful download, a software licence or an issuer fact-check
does not establish all rights needed for a production workflow. Actual account terms,
operator jurisdiction, purpose and onward use remain unverified. V1-DAT-001 stays blocked.
No provider has been contacted and no new agreement or paid subscription was created.

## Source register

| Source / affected use | Evidence found | Current release treatment / required resolution |
| --- | --- | --- |
| Yahoo through yfinance: financials, prices, peers, consensus; Agents 1–3 | [Official yfinance repository](https://github.com/ranaroussi/yfinance) describes research/educational use and Yahoo API personal use; underlying data terms are separate | Automated access, retained snapshots/backups, model input and report sharing remain pending. Obtain applicable Yahoo/account terms or a provider agreement covering the actual use |
| Yahoo Search news and linked publishers; Agent 3 | Headline access and article links do not establish publisher permissions. [Yahoo terms endpoint](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) returned HTTP 999 during review | No affirmative permission conclusion. Review applicable regional terms plus publisher rights for retained headline/snippet text, processing and sharing; do not infer article republication rights |
| ASML issuer filing and event evidence | [ASML terms](https://www.asml.com/en/terms-of-use) restrict copying/publication/distribution and commercial use absent applicable permission; source references prove provenance, not rights | No broad storage, model-input or redistribution approval established. Assess exact factual extraction versus document/text copying, applicable exceptions and licence/consent before release |
| Stadler Rail issuer filing; Agent 2 baseline | [Website notice, section 16](https://www.stadlerrail.com/api/docs/x/9c55debd67/website-privacy-notice-2024-en.pdf) permits personal duplication/printing and specifies a narrower News publication permission with attribution | Limited personal-copy evidence is not blanket commercial, model-processing or report-republication consent. Verify notice applicability/current version and intended use |
| Other issuers, event sources and datasets in historical acceptance | This review does not establish rights for NVIDIA, Apple, Rivian, Berkshire or future issuers merely because historical checks passed | Inventory exact URLs/files and terms individually before including their retained material in the release |
| Anthropic API; live model modes | [Commercial terms](https://www.anthropic.com/legal/commercial-terms) address API use, customer content ownership, no training on customer content and customer responsibility for input rights. [Retention explanation](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data) describes default API deletion within 30 days with exceptions | Verify actual account agreement and retention settings. No-training is not zero retention. Obtain authority to send each source/confidential input; API credentials alone do not supply that authority |
| Optional external Loughran–McDonald dictionary | [Official dictionary page](https://sraf.nd.edu/loughranmcdonald-master-dictionary/) allows free academic research use and directs commercial users to obtain a licence | Keep external dictionary commercial use unapproved until licensed. Repository curated subset is not verified as the official dictionary; review its provenance separately rather than asserting official coverage or permission |
| Optional ProsusAI/finbert | [Model card](https://huggingface.co/ProsusAI/finbert) identifies the model; this review does not establish a complete model/artifact licensing chain | Already deferred from production scope. Review exact pinned artifacts, dependencies and licence obligations before reconsideration |
| Agent 4 company budget/actuals | No authorised real-company dataset supplied | Require owner authorisation for local processing, backup retention, any model transfer and output audience; synthetic tests confer no company-data permission |
| Repository fixtures and software | Synthetic test inputs support local engineering validation. No root repository licence was found in the inspected tracked files | Do not infer third-party data licences or a public software distribution grant. Review dependencies and intended distribution separately before release |

## Approval record required for each dataset

Record source/provider and exact dataset identity; intended operator and purpose;
automated access method; raw and derived data retained; backup location/retention;
model provider and exact fields sent (or local-only); permitted output audience and
redistribution; governing agreement URL/version/date or protected contract reference;
obligations/attribution/deletion requirements; authorised reviewer and decision date.
Store confidential agreements outside public Git and reference their controlled location.

Use four separate decisions: access, retention/backup, model processing, and sharing.
A permission for one does not approve the others. Every decision must state allowed,
excluded or unresolved with evidence; limit the accepted workflow accordingly.
Inventory `permission: reviewed` is an operator metadata declaration, not an automated
legal decision. Record all applicable evidence before changing it from pending.

## Recommended next action

Continue engineering with synthetic fixtures. Before real production acceptance,
resolve the intended use and applicable Yahoo/source terms or select a licensed
provider whose agreement explicitly covers access, storage, model processing and
required report sharing. Do not assume that paying for a provider automatically
includes these rights. Private pilot use and customer-facing redistribution require
separate assessments. Existing live acceptance remains historical technical evidence,
not a newly approved production data entitlement.
