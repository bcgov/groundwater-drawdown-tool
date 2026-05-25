---
title: BCGW account help
parent: User Guide
nav_order: 3
---

# BCGW account help

The Groundwater Drawdown Tool signs in to BCGW with your **personal
BCGW account** — the same Oracle username and password you use for
other tools requiring a BCGW connection (e.g. ArcGIS Pro). If sign-in
is failing, the cause is almost always one of:

- the account is locked or expired,
- the password has expired or has just been changed,
- you are not on the BC government network or VPN — see
  [Troubleshooting]({{ site.baseurl }}{% link user-guide/troubleshooting.md %}).

This page covers how to check and fix the account itself.

## Check your account status

The BC government runs a self-serve query tool that reports the status
of any BCGW account:

**<https://apps.gov.bc.ca/int/aqt/jsp/query.jsp>**

1. In **User / Account Name**, enter your **IDIR** (no `@gov.bc.ca`).
2. In **Queries**, select **Account Status**.
3. In **Databases**, select **IDWPROD11** (the production BCGW database,
   the one the tool connects to).
4. Click **Submit**.

![BC Account Query Tool form, with the IDIR field filled, Queries set to Account Status, and Databases set to IDWPROD11]({{ site.baseurl }}/assets/img/bcgw-account-status-query.png)
*The BC Account Query Tool, with the three fields set to query an account's status.*

The result is the current status of your account:

| Status | Meaning |
|---|---|
| **OPEN** | Account is active. Sign-in should work. |
| **LOCKED** | Too many wrong-password attempts. See [Unlocking](#unlocking-a-locked-account) below. |
| **EXPIRED** | The password has expired. See [Changing your password](#changing-your-password). |
| **CLOSED** | The account no longer exists. Request a new one through the service desk. |

If the query reports no result for your IDIR you do not yet have a BCGW
account — request one through the NRM Business Service Desk.

## Changing your password

BCGW passwords expire and must be **updated every two months** to keep
the account active. The self-serve password-change tool is:

**<https://apps.gov.bc.ca/int/chorapwd/>**

Sign in with your IDIR and follow the prompts. After changing the
password, sign in to the Groundwater Drawdown Tool with the new
password — there is nothing to update inside the tool.

> **Tip:** Set a calendar reminder a few days before the two-month
> mark. Letting the password expire is the most common reason a
> previously-working sign-in suddenly stops working.

## Unlocking a locked account

**Three incorrect sign-in attempts will lock your BCGW account.** Once
locked, even the correct password no longer works — the lock has to be
cleared first.

To unlock the account, or to request a password reset if you have
forgotten the password, contact the **NRM Business Service Desk**:

- **Phone:** 7700 (internal), or the regular service-desk number on
  external lines.
- **Online ticket:**
  <https://apps.nrs.gov.bc.ca/int/jira/servicedesk/customer/portal/1/create/261>

In the ticket include your **IDIR**, the database name (**IDWPROD11**),
and a one-line description such as *"BCGW account locked, please
unlock"* or *"BCGW password reset request"*.

## Avoiding the lock

A few small habits prevent most account problems:

- Change your password before the two-month expiry — set a calendar
  reminder.
- After **two** failed sign-in attempts, stop and check the password
  before trying a third time. Use the account-status query above to
  confirm the account is still **OPEN** before attempting again.
- Your browser may have an old saved password from before your last
  password change. If it auto-fills incorrectly, clear the saved entry
  for `localhost:8050`.

## If sign-in still fails after all of this

See [Troubleshooting]({{ site.baseurl }}{% link user-guide/troubleshooting.md %}) for the
network/VPN checks. If the account is **OPEN**, your password is
known-correct, you are connected to the BC government network or VPN,
and sign-in still fails — contact your project lead.
