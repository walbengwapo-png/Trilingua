# TriLingua hosting options for adviser testing

Verified against official documentation on **19 October 2026 (Asia/Manila)**. The user confirmed that both Laravel and Python are deployed on Laravel Cloud, that the reported $5 monthly free allowance is exhausted, and that the next reset is **7 November**. Adviser testing is likely **20 October afternoon**, with a work cutoff described as “tomorrow 10”; the exact cutoff time is unconfirmed. These are user-reported account/timing facts. Actual resource sizes, invoice breakdown, account plan, and reset mechanics have not been independently verified. No accounts, billing settings, infrastructure, or application code were changed.

## Decision

**For the likely 20 October adviser test, restore the existing Laravel Cloud deployment with an agreed, bounded paid budget and rehearse it. Do not spend the remaining preparation window migrating hosts.** Check the account's actual plan and reason for suspension before selecting the restoration action. Use the local tunnel as the test-session fallback. Railway is a reasonable managed migration candidate after the test; Oracle is a longer-term low-cash-cost candidate after account acceptance, capacity allocation, ARM compatibility checks, and a rehearsal. These are judgments about deployment effort and failure modes, not measured performance comparisons.

Another path is a scheduled test from the existing local demo setup and its tunnel, while the PC and network remain online. Repository inspection found `start-all-demo-deploy.bat` → `start-demo.ps1 -Tunnel`. This avoids a migration for one supervised session, but is unsuitable for unattended adviser access and still needs a rehearsal and access control.

## Why an unused deployment still costs money

Not opening the app does not stop provisioned resources. Running web processes, database compute, queue workers, cache, and retained storage can all remain allocated. On Railway, memory held by running services costs money even while CPU use is low; on Laravel Cloud, running replicas accrue per-second compute charges. Storage has a separate meter. These billing models explain a possible idle bill; only the actual usage breakdown can establish which resources consumed this project's credits. [Railway pricing](https://railway.com/pricing), [Laravel Cloud pricing](https://laravel.com/cloud/docs/pricing).

For scale only: **1 GB RAM held continuously for 11 days costs approximately $3.67 on Railway**, using $0.00000386 per GB-second × 950,400 seconds. CPU, database RAM, other services, storage, egress, tax, and any plan minimum are separate. This is an illustration, not an estimate of the existing deployment's invoice. [Railway pricing](https://railway.com/pricing).

## Railway

- Hobby costs at least **$5/month**, including $5 of resource usage; excess usage is billed. The minimum is not an unlimited hosting bundle. RAM is $0.00000386/GB-second (roughly $10/GB for 30 days), CPU $0.00000772/vCPU-second (roughly $20 for a full vCPU for 30 days), and public egress $0.05/GB. [Pricing](https://railway.com/pricing).
- Set a **compute hard limit**, in addition to email alerts. Reaching it takes workloads offline; it trades availability for spend protection. Low resource limits can cause application failures, so measure a representative translation before choosing sizes. [Cost control](https://docs.railway.com/pricing/cost-control).
- Serverless sleep requires at least five minutes without outbound traffic. Database connections, polling and telemetry can prevent sleep. Incoming requests wake HTTP services; a polling-only worker has no incoming HTTP request to wake it. Do not assume enabling sleep makes the whole stack free while idle. [Serverless](https://docs.railway.com/deployments/serverless).

Repository inspection found a database queue default and a development launcher polling it every second. Railway sleep therefore needs specific verification with the production worker configuration. The normal translation path uses external GPT-OSS/Gemini inference; the optional NLLB loader is for controlled benchmarks. This does not establish measured RAM use or adviser-session latency.

## Oracle Cloud

### Current free allowance and availability

The current Always Free documentation specifies **1,500 OCPU-hours and 9,000 GB-hours of A1 memory per month**, equivalent to **2 OCPUs and 12 GB RAM continuously** for an Always Free tenancy. It also includes two small AMD instances and **200 GB combined boot/block storage** in the home region. Capacity shortages can prevent VM creation. Idle instances may be reclaimed if, over seven days, CPU 95th-percentile utilization and network utilization are below 20%, and A1 memory utilization is also below 20%. [Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

**Do not reuse the older blanket “4 cores/24 GB free” claim.** Oracle's current price list separately grants **paid tenancies** 3,000 OCPU-hours and 18,000 GB-hours monthly for A1, shared across VM, bare metal, and container instances. The free-account documentation and paid-tenancy allowance are different. Confirm the account's own entitlements before provisioning. [Oracle price list](https://www.oracle.com/cloud/price-list/).

### Card, charging and controls

Oracle accepts credit cards and debit cards that function as credit cards; its FAQ excludes PIN-based debit, virtual, single-use and prepaid cards. Temporary verification holds may occur. A card that works elsewhere is not evidence Oracle will accept it. Only one free account is allowed per person. [Free Tier FAQ](https://www.oracle.com/cloud/free/faq/).

The free trial provides up to $300 for 30 days. Oracle says the card is not charged unless the account is upgraded; paid trial resources are reclaimed if the user does not upgrade. Staying within Always Free resources avoids relying on expiring trial credit. [Free Tier documentation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm).

PAYG adds billing exposure above applicable free entitlements. **OCI budgets are soft limits with alerts, not a monetary shutdown cap**; published budget alerts are periodically evaluated, so they are not instantaneous protection. Resource quotas can restrict provisioning but are not a universal dollar cap. [Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm), [Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

Stopping a standard VM through the Console/API pauses its compute billing. An OS shutdown alone does not. Provisioned disks remain separate resources and can keep accruing charges outside free allowances; terminating a VM does not automatically mean all retained storage has been deleted. Preserve backups deliberately before deleting anything. [Stopped-instance billing](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/resource-billing-stopped-instances.htm), [Block Volume FAQ](https://www.oracle.com/cloud/storage/block-volumes/faq/).

### Operational tradeoff

An Oracle VM means taking responsibility for OS updates, firewall rules, HTTPS, PHP/Python services, a database, queue supervision, backups, and restart behavior. A1 is ARM, so dependencies must be installed and exercised there. There is no verified TriLingua A1 benchmark in this research. Oracle offers more memory within its free allocation than a small metered service, but that does not establish the app's throughput or reliability. Do not add artificial load to evade idle reclamation.

## Existing Laravel Cloud deployment

The user reports using a free $5/month mode. Current public documentation lists Starter at **$5/month with $5 monthly usage credit**, first 31 days free; excess usage can be billed. Credits reset each billing cycle. The account may have legacy terms: check its actual plan instead of treating the current new-account pricing as proof of this account's charges. [Plans and pricing](https://laravel.com/cloud/docs/pricing), [Free trial](https://laravel.com/cloud/docs/free-trial).

Only Flex compute can scale to zero. Inbound requests reset the sleep timer; scheduled tasks wake sleeping apps, and a wake interval shorter than the sleep timeout can keep an app awake continuously. Worker clusters can stay awake or follow the app. This makes scanners, monitors, schedules and worker settings relevant when diagnosing unexpected awake time. [Compute and Scale-to-Zero](https://laravel.com/cloud/docs/compute).

Queued jobs do not wake a sleeping app, and jobs still running when its sleep timeout expires can be interrupted. Simply switching sleep on is therefore unsafe for long translations without exercising the queue lifecycle. Moving to managed queues is an implementation choice requiring review, not a routine hosting checkbox. [Compute and Scale-to-Zero](https://laravel.com/cloud/docs/compute).

The current spending-limit screen defaults to **alerts only**. Enable **“Stop all compute”** for enforced shutdown: at the limit it pauses app, database and cache compute and blocks new provisioning. In-flight operations and retained object/database storage can create a small overage. Compute resumes automatically at the next cycle or when the limit is raised. If the deployment is paused by this feature, raising the limit can restore it before the next reset. This is a possible route, not confirmation of this account's state. [Spending limits](https://laravel.com/cloud/docs/spending-limits).

## Minimum next steps before paying or migrating

1. Inspect the current provider's usage by resource and the reason it stopped. Confirm whether the missing amount is free credit or a paid balance, and whether November 7 is a monthly credit refresh, plan renewal, or spend-limit reset.
2. Set the chosen provider's enforceable spend control and alert recipients before restoring compute. Keep database and file backups. Treat API/model-provider charges as separate unless the host explicitly includes them.
3. Rehearse one representative upload, translation, status polling, and final download using the adviser-facing URL; record resource use and latency. Choose resource sizes from this evidence.
4. For scheduled testing, stop compute immediately after the session and verify the provider reports it stopped. Review retained storage separately. If adviser access must remain available between sessions, budget for that explicitly instead of assuming idle means free.

The outstanding decisions are the acceptable restoration/monthly spend and exact test/cutoff time. No provider purchase or migration was performed.
