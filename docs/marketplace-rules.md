# KaaamNow Marketplace Rules (v1 draft)

Status: **final v1**.

All money examples use one shift: **₹100/hour × 8 paid hours = ₹800 worker pay**
("booking amount").

---

## 0. What KaaamNow is

- KaaamNow is a **connecting platform (intermediary)**. It connects someone who needs work
  done with a worker. KaaamNow is **not the employer** and does not supervise, perform or
  guarantee the work.
- The **"Business"** side (UI label: "Business / Work") can be a company, shop, office **or
  an individual person / household**. "Business" in this document means whoever posts the
  work.
- The agreement for the work is between the poster and the worker. KaaamNow handles
  matching, payments through escrow, the fee rules below, and support/mediation.
- The 4% commissions are a **platform service fee** for connecting and handling payment,
  not a share of wages.
- Disputes about work quality are between the two parties; support mediates and applies
  the rules in this document.
- Verification (v1): **mobile number OTP only** for every poster (individual or company).
  No ID upload and no admin approval needed to post. ID / business proof can be added later.

## 1. Accounts and roles

- One account can be both **Business / Work** (poster) and **Worker**. The user switches
  with a toggle in the app / web (backend already supports `active_role`).
- Each role keeps its own profile, verification, wallet view and history.
- A user can never apply to their own shift.

## 2. Terms & Conditions

- Business must accept the **Business T&C** before posting their first shift.
- Worker must accept the **Worker T&C** before applying to their first shift.
- Both T&Cs state that KaaamNow is only an intermediary (see §0) and is not the employer.
- Every acceptance stores: user, role, T&C version, timestamp, IP/device.
- When the T&C version changes, the user must accept again before the next post / apply.
- The cancellation, no-show, overtime and early-finish rules below are part of the T&C
  and are shown on a **fee preview screen** before any cancel action.
- In user-facing text these are called **"cancellation fees"**, not fines.

## 3. Shift flow (only flow)

```
Business posts + pays  →  Worker applies (= booked instantly)  →  Shift happens  →  Payout
```

- **No** business selection, **no** worker confirmation step.
- Live / instant shifts: code stays in place and is **not removed or hidden**. The existing
  "Post live request" button stays **disabled** as it is today (web business home already
  disables it in the Live view). No live-related changes in web or admin.
- Posting rules:
  - Shift must start **at least 24 hours** after posting.
  - Shift can be posted at most 60 days ahead (existing rule).
  - Business pays the full amount **at the time of posting** (see §4).
- Applying rules:
  - Applying is open until **2 hours before start**.
  - Only verified workers can apply.
  - A worker cannot hold overlapping shifts (existing check).
  - A banned worker cannot apply. A **negative wallet balance does not block applying**.
  - Max 5 upcoming bookings per worker at a time.
- If a booked worker cancels and more than 2 hours remain, the seat reopens for others.
- Business changing or dropping the plan = business cancellation (§6). Worker withdrawing
  = worker cancellation (§5). No other path.

### Notifications

- On posting, every available worker within **30 km** of the shift address (matching the
  work category) gets a **push notification**.

### Day of the shift

1. After booking, the worker sees the shift location on a map with **distance and route**
   (open in Google Maps), and can start travel (existing tracking).
2. Each booking has a **4-character alphanumeric code** (e.g. `K7P2`) shown only on the
   **business** side.
3. On arrival, the worker enters that code → check-in done → **work timer starts**.
4. At the booked end time, **either side** can end the shift.
5. To end **early**, the side ending it enters a **one-time PIN shown on the other
   side's app** (proof both agree). Early-finish payment rules: §8.
6. **Extension:** near the end time the app asks the business "Extend this shift?". The
   business enters extra time → the worker gets an **Accept** button → after accepting,
   work continues at the overtime rate (§7).

### Promo codes

- Admin creates promo codes from the admin panel, for **workers** or **businesses**.
- Each code has: target role, discount type (flat ₹ or %), what it discounts (commission
  / gateway charge), max discount, validity dates, total uses, uses per user, active flag.
- Business enters a code when posting; worker enters a code from their wallet (applies to
  the next payout's commission).
- The free-fees voucher (§9) is a system-generated promo code for one business.

### Unfilled shift at T−2h

- If not all seats are filled 2 hours before start, the unfilled seats are cancelled
  automatically.
- Business gets a **100% refund** for unfilled seats (worker pay + commission + gateway fee).
- Business also gets a **free-fees voucher** for the next shift (see §9).
- Filled seats continue normally.

## 4. Fees and payment

- Platform fee: **0**.
- Commission: **4% from business + 4% from worker**, calculated on the booking amount.
- Payment gateway charge (~2%): **paid by business**, added on top.
- All money moves through the platform. Business pays upfront into escrow; worker is paid
  out after the shift is approved.

Example (₹800 booking):

| Line | Amount |
|---|---|
| Worker pay (booking amount) | ₹800 |
| Business commission 4% | ₹32 |
| Gateway ~2% on ₹832 | ~₹17 |
| **Business pays at posting** | **~₹849** |
| Worker commission 4% | −₹32 |
| **Worker receives** | **₹768** |
| Platform earns | ₹64 |

On any cancellation, the gateway charge is non-refundable; commission is
refunded together with the refundable part of the booking amount.

## 5. Worker cancellation

Fees are charged to the worker's wallet. If the wallet does not have enough, the balance
goes **negative** and is recovered automatically from the worker's next earnings (when a
business pays for a completed shift, the due amount is deducted before payout). The
worker can keep applying and working while negative.

| Time before start | Worker pays |
|---|---|
| More than 12h | Free |
| 12h – 6h | ₹49 |
| 6h – 2h | ₹89 |
| Less than 2h | ₹149 + **½ strike** |
| No-show (no cancel, no info) | 50% of booking, max ₹399 + **1 strike** |

- **Strikes (within 90 days):** 2 strikes = fewer shifts shown for 7 days; 3 strikes =
  account ban (admin can review).
- When a worker cancels inside 2h or doesn't show up, the business gets a full refund
  **plus** a free-fees voucher (§9).
- Worker cancellation fees go to the platform (business is compensated by the
  refund + voucher).

## 6. Business cancellation

Percentages are of the booking amount (₹800). The business's refund is whatever is left of
what they paid after the fee.

| Time before start | Business pays | Of which, to worker |
|---|---|---|
| More than 12h | Free | — |
| 12h – 6h | 50% (₹400) | 30% (₹240) |
| 6h – 2h | 70% (₹560) | 40% (₹320) |
| Less than 2h | 100% (₹800) | 80% (₹640) |

- The remaining part of the fee stays with the platform.
- Worker compensation goes to the worker's wallet with no commission deducted.
- If the shift has no booked worker yet, cancellation is always free (full refund).

## 7. Overtime

- If work runs past the booked end time, overtime is paid at **130%** of the hourly rate.
- Overtime counts only if the **business approves it in the app** (on the
  worker's checkout or a "extend shift" request). Unapproved extra time is not paid.
- Overtime is not covered by escrow; it is charged to the business after the shift
  (same 4% commission + gateway charge), and paid to the worker after it's collected.

## 8. Early finish and walk-off

| Case | Business pays | Worker gets |
|---|---|---|
| Both agree to finish early | Actual worked hours | Actual worked hours − 4% |
| Business stops the work / denies work without reason | 100% of booking | 80% of booking (remaining 20% to platform) |
| Worker walks off / refuses to work | Actual worked hours only | Worked hours − 4%, minus penalty of 50% of booking amount |

- When the worker walks off, the business also gets a free-fees voucher (§9).
- Disputes ("who denied") go to support; admin decides and can override fees.

## 9. Free-fees voucher

- Issued to the business when: a worker no-shows, a worker cancels inside 2h, a worker
  walks off, or seats go unfilled at T−2h.
- Waives **both commission and gateway charge** on the next shift (one shift only).
- Valid for 60 days, not transferable, not cash.

## 10. Emergencies and support

- Every booking has an **Emergency → Contact support** button (app + web).
- It creates a high-priority support ticket with the shift and both parties attached.
- Admin can waive or change any fee, strike or voucher for that booking, with a reason
  that is logged.

## 11. Admin needs

- Edit all values above (percentages, flat fees, time tiers, strike limits) without a
  code deploy, versioned like the existing `platform_fee_policies`.
- Ledger view per booking: payments, refunds, fees, compensation, vouchers.
- Worker negative balances, strikes and bans.
- T&C versions and acceptance records.
- Dispute / emergency ticket queue.