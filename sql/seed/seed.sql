-- Idempotent reference data applied on every API boot (ON CONFLICT DO NOTHING).
-- Copy comes from the KaaamNow Figma file; marketplace values are OWNER DECISIONS.

-- Figma SH · Language
INSERT INTO languages (code, english_name, native_name, sort_order) VALUES
    ('en', 'English',   'English',   1),
    ('hi', 'Hindi',     'हिन्दी',      2),
    ('ta', 'Tamil',     'தமிழ்',      3),
    ('te', 'Telugu',    'తెలుగు',     4),
    ('kn', 'Kannada',   'ಕನ್ನಡ',      5),
    ('ml', 'Malayalam', 'മലയാളം',    6),
    ('mr', 'Marathi',   'मराठी',      7),
    ('bn', 'Bengali',   'বাংলা',      8),
    ('gu', 'Gujarati',  'ગુજરાતી',    9),
    ('pa', 'Punjabi',   'ਪੰਜਾਬੀ',     10),
    ('or', 'Odia',      'ଓଡ଼ିଆ',      11),
    ('ur', 'Urdu',      'اردو',      12)
ON CONFLICT (code) DO NOTHING;

-- Figma "Work type" / "Business type" chips, plus unorganised-sector daily work.
INSERT INTO work_categories (slug, name, icon, sort_order) VALUES
    ('hospitality',      'Hospitality',              'coffee',        1),
    ('retail',           'Retail',                   'shopping-bag',  2),
    ('events',           'Events',                   'calendar',      3),
    ('delivery',         'Delivery',                 'truck',         4),
    ('house-help',       'House Help / Maid',        'home',          5),
    ('cooking',          'Cook',                     'chef-hat',      6),
    ('cleaning',         'Cleaning',                 'sparkles',      7),
    ('babysitting',      'Babysitting / Nanny',      'baby',          8),
    ('elder-care',       'Elder Care',               'heart-handshake', 9),
    ('driver',           'Driver',                   'car',           10),
    ('security',         'Security Guard',           'shield',        11),
    ('construction',     'Construction Labour',      'hard-hat',      12),
    ('loading',          'Loading / Unloading',      'package',       13),
    ('warehouse',        'Warehouse Helper',         'warehouse',     14),
    ('gardening',        'Gardening',                'leaf',          15),
    ('painting',         'Painter',                  'paintbrush',    16),
    ('plumbing',         'Plumber',                  'wrench',        17),
    ('electrician',      'Electrician',              'zap',           18),
    ('carpentry',        'Carpenter',                'hammer',        19),
    ('tailoring',        'Tailoring',                'scissors',      20),
    ('laundry',          'Laundry / Ironing',        'shirt',         21),
    ('kitchen-helper',   'Kitchen Helper',           'utensils',      22),
    ('waiter',           'Waiter / Server',          'concierge-bell', 23),
    ('shop-helper',      'Shop Helper',              'store',         24),
    ('office-boy',       'Office Assistant / Peon',  'briefcase',     25),
    ('car-wash',         'Car Wash',                 'droplets',      26),
    ('pet-care',         'Pet Care',                 'paw-print',     27),
    ('other',            'Other',                    'more-horizontal', 99)
ON CONFLICT (slug) DO NOTHING;

-- OWNER DECISION: Figma shows an illustrative 5% fee paid by the business on top of worker pay.
INSERT INTO platform_fee_policies (version, percentage, is_active, notes)
SELECT 1, 5.00, true, 'DEV DEFAULT from Figma copy (5% on top of worker pay). Confirm before launch.'
WHERE NOT EXISTS (SELECT 1 FROM platform_fee_policies);

-- Terms & Conditions (worker + business share the Figma copy dated 1 October 2026)
INSERT INTO content_pages (slug, audience, title, body_markdown, effective_date) VALUES
    ('terms', 'worker', 'Terms & Conditions',
     E'## 1. Using KaaamNow\nKaaamNow connects businesses with workers for short shifts. By creating an account you agree to these terms and to use the app lawfully.\n\n## 2. Accounts and verification\nYou must give accurate details. Phone numbers are verified by OTP, and businesses may be asked for extra verification.\n\n## 3. Shifts, payments and cancellations\nPay rates are shown before you accept a shift. Payments are released after check-out. Late cancellations may affect your rating.\n\n## 4. Ratings and conduct\nBusinesses and workers rate each other after every shift. Harassment, fake check-ins or no-shows can lead to suspension.\n\n## 5. Privacy and data\nWe use your location only to show nearby shifts and track check-in. See the Privacy Policy for details.\n\n## 6. Contact us\nQuestions about these terms? Write to sumit.pandey@kaaamnow.in or sahil.shrivastava@kaaamnow.in.',
     DATE '2026-10-01'),
    ('terms', 'business', 'Terms & Conditions',
     E'## 1. Using KaaamNow\nKaaamNow connects businesses with workers for short shifts. By creating an account you agree to these terms and to use the app lawfully.\n\n## 2. Accounts and verification\nYou must give accurate details. Phone numbers are verified by OTP, and businesses may be asked for extra verification.\n\n## 3. Shifts, payments and cancellations\nPay rates are shown before workers accept a shift. You pay the final shift cost after reviewing attendance. Late cancellations may affect your rating.\n\n## 4. Ratings and conduct\nBusinesses and workers rate each other after every shift. Harassment, unsafe workplaces or non-payment can lead to suspension.\n\n## 5. Privacy and data\nWorker location is shared with you only while a booked worker is travelling to or checking in at your workplace.\n\n## 6. Contact us\nQuestions about these terms? Write to sumit.pandey@kaaamnow.in or sahil.shrivastava@kaaamnow.in.',
     DATE '2026-10-01')
ON CONFLICT (slug, audience) DO NOTHING;

-- FAQ & Help
INSERT INTO faq_entries (audience, question, answer, sort_order) VALUES
    ('worker', 'How do I get paid?',
     'After you check out, the business confirms the shift and your earnings are sent to your UPI or bank account within 24 hours.', 1),
    ('worker', 'How do I cancel a shift?',
     'Open My shifts, choose the shift and tap Cancel. Cancelling less than 12 hours before the start may affect your rating.', 2),
    ('worker', 'How does check-in work?',
     'When you are near the workplace, open the shift and enter the workplace code from your shift lead. Your location is used only to verify attendance.', 3),
    ('worker', 'What if the business doesn’t show up?',
     'Use “I need help checking in” on the shift. Our team will contact the business and keep your earnings safe.', 4),
    ('worker', 'How are ratings calculated?',
     'Your rating is the average of the stars businesses give you after each completed shift.', 5),
    ('business', 'How do I pay for a shift?',
     'After workers check out, review attendance and confirm the final shift cost. Pay with Google Pay, Paytm, UPI QR or card.', 1),
    ('business', 'How do I cancel a shift?',
     'Open Shifts, choose the shift and tap Cancel. Booked workers are notified immediately.', 2),
    ('business', 'How does check-in work?',
     'Each shift has a workplace code. Share it with workers on arrival; they must also be near your workplace to check in.', 3),
    ('business', 'What if a worker doesn’t show up?',
     'After the start time you can mark the worker as a no-show from the roster. You are not charged for no-shows.', 4),
    ('business', 'How are ratings calculated?',
     'Your rating is the average of the stars workers give you after each completed shift.', 5)
ON CONFLICT (audience, question) DO NOTHING;
