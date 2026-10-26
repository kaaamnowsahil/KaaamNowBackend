# Implementation plan for marketplace rules v1

Rules: `docs/marketplace-rules.md`. Order: Backend → Mobile app → Web → Admin.
Live-shift code stays untouched everywhere (button stays disabled).

---

## Backend (`KaaamNowBackend`)

### 1. One-step booking
- `application_service.apply` creates the assignment directly as `confirmed`
  (reuse `_book_selected`); seat + overlap + ban + max-5 checks in the same transaction.
- Shift moves `open → filled` when seats are full, back to `open` when a seat frees up.
- `select` / `reject` / `confirm` / `decline` endpoints stay but are no longer used by UIs.
- Apply closes at T−2h.

### 2. Posting rules + pay on post
- `validate_window`: scheduled shift must start ≥ 24h from now (setting, not hardcoded).
- New shift status `awaiting_payment`: create → pay (existing `payment_service`) →
  `open`. Payment webhook/confirm publishes the shift.
- Estimate shows booking amount, 4% commission, gateway charge, promo discount.

### 3. Fee model
- Extend `platform_fee_policies`: `business_commission_pct`, `worker_commission_pct`,
  `gateway_pct`, platform fee 0. Snapshot on the shift at posting (existing pattern).
- Invoice lines: worker pay, business commission, gateway, promo discount.
- Worker earning ledger: gross pay, worker commission, recovered dues.

### 4. Cancellation engine
- New table `cancellation_policies` (versioned): tiers per role with time window, flat ₹ /
  %, cap, worker-compensation %, strike weight. Seeded with the v1 values.
- Pure function `quote_cancellation(role, assignment, now)` → fee, worker compensation,
  refund, strike. Used by a new **preview** endpoint and by the cancel endpoints.
- Business cancel: refund to business, compensation to worker wallet, rest to platform.
- Worker cancel: fee to worker wallet (may go negative), seat reopens if > 2h left,
  voucher to business when inside 2h.
- No-show (existing `mark_no_show`) and walk-off use the same engine.

### 5. Wallet dues + strikes
- Earning ledger allows negative balance; payout deducts dues first.
- New table `worker_strikes` (weight 0.5 / 1, expires after 90 days). 2 → reduced feed
  for 7 days, 3 → `users.is_active = false` pending admin review.

### 6. Promo codes
- Tables `promo_codes`, `promo_redemptions`.
- Validate endpoint per role; applied at posting (business) or next payout (worker).
- System vouchers = promo codes with `owner_user_id` set, single use, 60 days.

### 7. Push within 30 km
- `scheduled_notify_radius_km` → 30; on publish, enqueue notifications for matching
  available workers (existing outbox + `deliver_pending_pushes`).
- Implement FCM push sender in `push_sender_factory` (`push_provider=fcm`).

### 8. Check-in code + timer
- Code per **assignment**, 4-char alphanumeric (no 0/O/1/I), visible only to the
  business in assignment detail. `check_in` compares against it; check-in time = timer start.

### 9. Ending the shift
- At/after end time: either side can call `check_out`.
- Early end: `POST /assignments/{id}/end-early/pin` (shows PIN to the other side) and
  `POST /assignments/{id}/end-early` (side ending enters PIN, with reason
  `mutual` / `business_stopped` / `worker_left`). Payment per rules §8.

### 10. Extension
- Table `shift_extensions` (assignment, extra minutes, status `requested/accepted/declined`).
- Notification to business ~15 min before end; business requests minutes; worker accepts;
  `ends_at` for the assignment extends; overtime billed at 130% after the shift.

### 11. Sweeps
- T−2h: cancel unfilled seats, refund, issue voucher.
- Expire strikes, expire vouchers, extension reminders.

### 12. T&C acceptance
- Table `terms_acceptances` (user, role, version, accepted_at, ip, device).
- Post / apply return `terms_required` until the current version is accepted.

### 13. Support
- Emergency button = support ticket with `priority = urgent` and the assignment attached.

---

## Mobile app (`KaaamNowApp`, React Native)

- **Role toggle** in profile/header (business ↔ worker), uses existing `active_role`.
- **Push:** add `@react-native-firebase/messaging`, register token to `user_devices`,
  open the shift on tap.
- **Business**
  - Post shift: 24h-min date picker, price breakdown, promo code field, pay → posted.
  - Applicants screen becomes **Booked workers** (no approve button).
  - Booking detail: check-in code, worker live location, end shift, early-end PIN,
    extend dialog, cancel with fee preview.
- **Worker**
  - Feed → shift detail → **Apply** (one tap, T&C sheet first time) → booked screen.
  - Remove `shiftSelected` confirm step from the flow.
  - Booking: map with distance + "Open in Google Maps", start travel, enter check-in
    code, running timer, end shift / early-end PIN, accept extension, withdraw with
    fee preview.
  - Wallet: negative dues, strikes, promo code entry.
- Emergency support button on every booking.

## Web (`KaaamNowWeb`)

Same business + worker changes as the app, on existing pages:
- `businessShiftCreate` (24h rule, breakdown, promo, pay), `businessApplicants` → booked
  workers, `businessScheduledWorkerTracking` (code, end, PIN, extend), `shiftDetails` /
  `workerBooking` (one-tap apply, T&C), `shiftCheckIn`, `finishShift`, `shiftSelected`
  removed from flow, role toggle in header, cancel fee preview.
- Live button stays disabled as today. Push on web: in-app notifications only.

## Admin (`KaaamNowAdmin`)

- **Promo codes** page: create / edit / deactivate, usage stats.
- **Policies** page: commission %, gateway %, cancellation tiers, strike limits, notify
  radius, posting minimum hours (versioned).
- Worker detail: wallet dues, strikes, unban.
- Booking ledger view: payment, refunds, fees, compensation, vouchers.
- Support: urgent/emergency queue, fee override with reason.
- T&C versions + acceptance records.

---

## Delivery order

1. Backend 1, 2, 3, 12 (core flow + money in).
2. Backend 4, 5, 11 (cancellation + sweeps).
3. Backend 7, 8, 9, 10 (day-of-shift).
4. Backend 6, 13 (promos, support).
5. App + Web screens in the same order.
6. Admin pages.
