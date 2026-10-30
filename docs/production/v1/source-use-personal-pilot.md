# Source-use review — private personal pilot

Reviewed 13 October 2026 against code `78504efeffa043cf485d58106b8503c7fe456989`.
The user selected **private personal evaluation only**, one analyst, local outputs,
no employer/client use and no external sharing. This is a documented permissions
assessment, not a legal opinion or provider consent. V1-DAT-001 remains blocked.
The interpretation review is deferred at the user's request; execution evidence
from the eight-task trial does not supply data rights or human financial sign-off.

## Decision boundary

The accompanying [permission register](../../../references/acceptance/source-permissions-2026-10-13.json)
separates access, retention/backup, local processing, external-model processing and
sharing. `supported_limited` means published evidence supports only the described
narrow act, subject to applicability and conditions; it does not approve the full
agent workflow. `unresolved` means the required entitlement was not established.
`excluded_scope` means outside this selected review scope, not necessarily legally
prohibited. `engineering_only` describes the existing synthetic rehearsal boundary.
No runtime inventory is promoted to `permission: reviewed` by this assessment.

External model transfer and report sharing are excluded from the recommended local
pilot workflow while their permissions remain unresolved. The user selected local
outputs; that selection alone does not establish that cloud inference is permitted.
Existing paid/live opt-ins are technical controls, not permission attestations.
This batch does not add a runtime rights gate, remove adapters, purchase data,
contact providers, transfer raw datasets, delete evidence or approve a release.

## Findings and recommended treatment

| Source | Published evidence / actual use | Personal-pilot treatment |
| --- | --- | --- |
| Yahoo via yfinance | The [project README](https://github.com/ranaroussi/yfinance) describes personal/research use but directs users to Yahoo for data rights. The indexed [Yahoo terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html?ncid=mbr_idnedulnk00000001) include a restriction on automated collection without prior permission. Direct US and Ireland terms retrieval returned HTTP 999; the regional agreement is not verified. | Do not approve Keystone's automatic financial, price, consensus or news access from the README alone. Obtain applicable account/region terms and express API permission, or a licensed alternative. Saved-data processing and retention remain unresolved. |
| Yahoo news / publishers | `agent3/news_live.py` retains headlines, provider summaries, timestamps, publisher labels and URLs; it does not fetch full article pages. Both retained 20-item acceptance bundles link through finance.yahoo.com. | Links do not establish rights in syndicated text. Require a feed grant covering headline/summary storage, local analysis and backup. Publisher permissions remain unassessed; do not treat the 40-item labelling pack as approved content for redistribution. |
| ASML filing and dates | [Website terms](https://www.asml.com/en/terms-of-use) reserve rights and restrict publication/distribution and commercial copying. No explicit grant covering this automated retention/analysis workflow was established. | Local factual extraction versus copied document/text needs a scoped assessment; do not characterize all personal reading or factual use as prohibited. Require exact host/document terms or permission before approving automated use. `ourbrand.asml.com` annual-report hosting must be included. |
| Stadler filing | [November 2024 website notice, §16](https://www.stadlerrail.com/api/docs/x/9c55debd67/website-privacy-notice-2024-en.pdf) permits personal duplication/printing; separate publication language applies to News content. | Limited evidence supports a personal copy. Verify notice applicability to the FY2025 PDF and preserve notices. Automated collection, backup arrangements and processing rights beyond personal copying remain unresolved; a filing is not automatically News content. This does not approve Yahoo monitoring inputs. |
| NVIDIA issuer evidence | [Current redirected site terms, §§3–4](https://www.nvidia.com/en-eu/about-nvidia/terms-of-service/) offer a single-computer personal non-commercial download option and restrict automated extraction. | Limited personal download support only where these terms apply. Verify investor-site/document applicability. No grant for automated collection, additional backup copies or model transfer established. |
| GlobeNewswire event-date references | Both frozen event plans cite press releases hosted by GlobeNewswire, independently of their issuer. The [site](https://www.globenewswire.com/) describes distribution services; applicable reader/API licensing terms were not located in this review. | Keep the host-specific rights question open. Issuer authorship and public distribution are not a demonstrated automated-use licence. Request governing reader/feed terms if including these sources. |
| Euronext benchmark identity | [Data policy](https://www.euronext.com/en/data/real-time-data/pricing-specs-agreements/market-data-pricing-policies) distinguishes display/non-display uses and says internal delayed-data use is free of charge while referring to agreements. | A fee statement does not approve Keystone's entire workflow. Current plans use the Euronext page for benchmark identity; price series come through Yahoo. Assess identity references separately from series, derived statistics, retention and AI rights. |
| S&P benchmark identity | [Terms](https://www.spglobal.com/en/terms-of-use) describe personal non-commercial SPDJI use with additional restrictions and controlling [SPDJI disclaimers](https://www.spglobal.com/spdji/en/disclaimers/). | Do not infer permission for historical databases or derived data from personal-use language. Existing S&P reference identifies the benchmark, not a directly licensed price feed. Series remain dependent on Yahoo rights. |
| Anthropic API | [Commercial terms](https://www.anthropic.com/legal/commercial-terms) govern API-key use. [Retention guidance](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data) describes standard deletion within 30 days, with exceptions including Files API, agreements, enforcement and legal retention. | Keep cloud inference outside this local review's approved workflow. Before enabling, verify actual account agreement/settings, source-specific transfer rights and exact payload. Neither credentials nor a no-training statement establish zero retention or input rights. |
| External LM dictionary | [Official page](https://sraf.nd.edu/loughranmcdonald-master-dictionary/) expressly covers free academic research and directs commercial licensing enquiries. | Private personal evaluation is not automatically academic research. Obtain applicable permission before using an external CSV. The repository-curated subset is explicitly not a verified official dictionary; its provenance remains a separate review item. |
| FinBERT | Already deferred from production scope. | Keep excluded; no new model licence or artifact-chain approval claimed here. |
| Company FP&A / historical other issuers | Authorised company data is unavailable; AAPL/RIVN/BRK-B historical summaries do not establish source rights. | Keep company-data acceptance blocked. Review actual sources for any future inclusion; being personal does not authorise use of employer/client confidential data. |
| Synthetic inputs / project software | Existing fixtures are labelled illustrative; no root software licence is tracked. | Continue the established offline engineering scope. The absence of a root licence is a distribution/licensing follow-up, not by itself a reason the owner cannot execute the local project. Fixture labels alone are not proof of ownership of all embedded text. No third-party dataset or public software redistribution approval is inferred. |

## Actual data paths checked

- `tools/data.py`: yfinance financials, prices, history, consensus and trends.
- `agent3/track_a_live.py`: provider dates, prices and peer identities. Frozen ASML
  and NVIDIA plans add distinct issuer/newswire/benchmark evidence URLs.
- `agent3/news_live.py`: Yahoo Search response and normalized headline/summary
  records; the raw response is retained in evidence. Yahoo-hosted links do not settle
  the rights of the publishers named in those records.
- `agent/loop.py` serializes tool outputs into conversation messages;
  `agent/models.py` sends messages/system/tool definitions to Anthropic. A local HTML
  destination therefore does not make an enabled live-model run local-only.
- `agent3/lm_lexicon.py`: optional `LM_DICTIONARY_CSV` versus curated subset. Neither
  a configured path nor a successful load is evidence of a dictionary licence.
- `keystone/storage.py`: copies declared sources into local snapshots; the current
  storage policy neither encrypts them itself nor supplies retention rights.

The machine-readable register records source paths and hashes plus the exact URLs
already embedded in the issuer/reference plans. It does not copy filings, headlines,
full contracts or private account records into Git. Access dates are review dates,
not an assertion that mutable terms had a particular historical effective version.
Yahoo evidence is explicitly search-index evidence; no regional applicability is
inferred from the user's current timezone or travel location.

## Remaining actions to clear V1-DAT-001

1. **Recommended first:** resolve the live Yahoo dependency. Provide the governing
   account/region agreement and any express API grant, or compare providers against
   the requirements below. A paid plan alone is insufficient. No provider selection
   or purchase is made by this review.
2. For each included filing/date source, bind the exact file/URL to applicable terms
   and the intended acts. Confirm copied text, facts, charts and derived calculations
   separately. A qualified reviewer can assess an applicable exception where no
   express grant exists; this review does not assume one.
3. Resolve backup retention, permitted copies, deletion obligations and licence
   expiry. No arbitrary retention period or automatic deletion is introduced.
   Previously retained evidence stays local pending review; that is not an assertion
   of indefinite lawful retention or new permission to expand the collection.
4. Keep external sharing and model transfer out of the selected workflow until
   expressly assessed. Any future employer/client/customer use triggers a fresh review.
5. Record reviewer, decision date, exact evidence and conditions for every included
   source and right. Only then update permission metadata and the release gate.

## Provider/permission requirements ready for use

For a potential provider or rights-holder, specify one private individual, one local
computer and no redistribution. Ask whether the agreement permits: automated API
retrieval; annual statements, prices, consensus and relevant news as applicable;
raw snapshots and derived reports; local historical replay and disaster-recovery
copies; non-display analytical calculations; retention duration and post-termination
handling. Require explicit attribution, rate, exchange and publisher restrictions.
Ask about external inference separately if later needed; it is excluded for now.
Keep any account identifier or private agreement out of public Git. Nothing has
been sent to a provider, and this checklist is not consent to contact anyone.

## Outcome

Public-terms review completed for the bounded personal pilot with named evidence
limitations. **No live-source workflow is newly approved, and V1-DAT-001 remains
blocked.** Narrow personal-copy evidence is recorded without extrapolating it to
all of Keystone. Runtime behaviour and existing release claims are unchanged.

## Yahoo dependency follow-up

The user confirmed no existing data licence. The [resolution assessment](yahoo-dependency-resolution.md) recommends an official Yahoo developer/API enquiry first, with EODHD as a candidate fallback. A [provider enquiry](provider-permission-enquiry.md) is prepared but unsent. No entitlement or provider selection is approved; V1-DAT-001 remains blocked.

**30 October contact update:** the [Yahoo enquiry record](yahoo-finance-enquiry.md)
documents the general support route and the user's reported submission of the short
routing request. Its case number is unavailable and a reply is pending. The detailed
draft remains unsent; this update does not change the 13 October permission findings.
