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
    ('cook',             'Cook (Hotel / Restaurant)', 'chef-hat',     28),
    ('hotel-staff',      'Hotel Staff',              'bed',           29),
    ('ac-technician',           'AC Technician / Repair',          'air-vent',        30),
    ('appliance-repair',        'Appliance Repair Technician',     'plug',            31),
    ('ro-technician',           'RO / Water Purifier Technician',  'droplet',         32),
    ('pest-control',            'Pest Control Worker',             'bug',             33),
    ('deep-cleaning',           'Deep Cleaning',                   'spray-can',       34),
    ('chef',                    'Chef / Head Cook',                'chef-hat',        35),
    ('dishwasher',              'Dishwasher / Kitchen Steward',    'utensils-crossed', 36),
    ('catering-staff',          'Catering Staff',                  'utensils',        37),
    ('barista',                 'Barista',                         'coffee',          38),
    ('cashier',                 'Cashier / Billing Staff',         'receipt',         39),
    ('sales-executive',         'Sales Executive',                 'trending-up',     40),
    ('storekeeper',             'Storekeeper',                     'boxes',           41),
    ('inventory-assistant',     'Inventory Assistant',             'clipboard-list',  42),
    ('receptionist',            'Receptionist / Front Desk',       'bell',            43),
    ('data-entry',              'Data Entry Operator',             'keyboard',        44),
    ('computer-operator',       'Computer Operator',               'monitor',         45),
    ('customer-support',        'Customer Support Executive',      'headphones',      46),
    ('bike-delivery',           'Bike Delivery Partner',           'bike',            47),
    ('courier',                 'Courier / Parcel Delivery',       'package',         48),
    ('picker-packer',           'Picker / Packer',                 'package-check',   49),
    ('forklift-operator',       'Forklift Operator',               'forklift',        50),
    ('factory-helper',          'Factory Helper',                  'factory',         51),
    ('machine-operator',        'Machine Operator',                'cog',             52),
    ('production-line',         'Production Line Worker',          'settings',        53),
    ('packaging',               'Packaging Worker',                'package-open',    54),
    ('quality-checker',         'Quality Checker',                 'badge-check',     55),
    ('mason',                   'Mason / Raj Mistri',              'brick-wall',      56),
    ('tile-fitter',             'Tile / Marble Fitter',            'grid-3x3',        57),
    ('welder',                  'Welder',                          'flame',           58),
    ('fabricator',              'Fabricator',                      'wrench',          59),
    ('false-ceiling',           'False Ceiling Worker',            'layers',          60),
    ('glass-fitter',            'Glass / Aluminium Fitter',        'square',          61),
    ('construction-supervisor', 'Construction Supervisor',         'hard-hat',        62),
    ('event-setup',             'Event Setup Crew',                'tent',            63),
    ('sound-light',             'Sound / Light Technician',        'speaker',         64),
    ('photographer',            'Photographer / Videographer',     'camera',          65),
    ('housekeeping',            'Housekeeping Staff',              'bed-double',      66),
    ('facility-maintenance',    'Facility Maintenance Technician', 'hammer',          67),
    ('beautician',              'Beautician / Salon Staff',        'sparkle',         68),
    ('barber',                  'Hairdresser / Barber',            'scissors',        69),
    ('makeup-artist',           'Makeup Artist',                   'brush',           70),
    ('mobile-repair',           'Mobile Repair Technician',        'smartphone',      71),
    ('it-technician',           'Computer / IT Technician',        'laptop',          72),
    ('tutor',                   'Tutor / Home Tutor',              'book-open',       73),
    ('waste-collection',        'Waste Collection Worker',         'trash-2',         74),
    ('other',            'Other',                    'more-horizontal', 99)
ON CONFLICT (slug) DO NOTHING;

-- Business / Work type chips: one list for households and commercial hirers alike.
INSERT INTO business_types (slug, name, icon, sort_order) VALUES
    ('household',             'Household',                         'home',            1),
    ('personal-residence',    'Personal Residence',                'house',           2),
    ('apartment',             'Apartment / Flat',                  'building-2',      3),
    ('independent-house',     'Independent House / Villa',         'house-plus',      4),
    ('rental-property',       'Rental Property',                   'key-round',       5),
    ('residential-society',   'Residential Society',               'building',        6),
    ('office',                'Office',                            'briefcase',       7),
    ('corporate-office',      'Corporate Office',                  'landmark',        8),
    ('hospitality',           'Hospitality',                       'coffee',          9),
    ('retail',                'Retail',                            'shopping-bag',    10),
    ('events',                'Events',                            'calendar',        11),
    ('delivery',              'Delivery',                          'truck',           12),
    ('restaurant',            'Restaurant / Cafe',                 'utensils',        13),
    ('hotel',                 'Hotel / Guest House',               'bed',             14),
    ('catering',              'Catering',                          'chef-hat',        15),
    ('grocery',               'Grocery / Kirana Store',            'shopping-cart',   16),
    ('supermarket',           'Supermarket / Mall',                'store',           17),
    ('warehouse',             'Warehouse / Logistics',             'warehouse',       18),
    ('manufacturing',         'Factory / Manufacturing',           'factory',         19),
    ('construction',          'Construction',                      'hard-hat',        20),
    ('real-estate',           'Real Estate / Property Management', 'building',        21),
    ('healthcare',            'Hospital / Clinic',                 'stethoscope',     22),
    ('education',             'School / Coaching',                 'graduation-cap',  23),
    ('college',               'College / University',              'school',          24),
    ('salon',                 'Salon / Spa',                       'scissors',        25),
    ('gym',                   'Gym / Fitness Center',              'dumbbell',        26),
    ('cleaning',              'Cleaning / Facility Management',    'sparkles',        27),
    ('security',              'Security Services',                 'shield',          28),
    ('automobile',            'Automobile / Garage',               'car',             29),
    ('car-wash',              'Car Wash',                          'droplets',        30),
    ('laundry',               'Laundry / Dry Cleaning',            'shirt',           31),
    ('bakery',                'Bakery / Sweet Shop',               'cake',            32),
    ('pharmacy',              'Pharmacy',                          'pill',            33),
    ('ecommerce',             'E-commerce',                        'package',         34),
    ('agriculture',           'Farm / Agriculture',                'leaf',            35),
    ('wedding',               'Wedding / Banquet Hall',            'party-popper',    36),
    ('travel',                'Travel / Tourism',                  'plane',           37),
    ('call-center',           'Call Center / BPO',                 'headset',         38),
    ('it-software',           'IT / Software Company',             'laptop',          39),
    ('professional-services', 'Professional Services',             'briefcase-business', 40),
    ('ngo',                   'NGO / Non-profit',                  'hand-heart',      41),
    ('small-business',        'Shop / Small Business',             'store',           42),
    ('other',                 'Other',                             'more-horizontal', 99)
ON CONFLICT (slug) DO NOTHING;

-- Bring rows seeded by the earlier list to the new names and order. A row an admin has since
-- renamed or reordered no longer matches its old values and is left alone.
UPDATE business_types bt
SET name = v.new_name, sort_order = v.new_sort, updated_at = now()
FROM (VALUES
    ('hospitality',   'Hospitality',             1,  'Hospitality',                       9),
    ('retail',        'Retail',                  2,  'Retail',                            10),
    ('events',        'Events',                  3,  'Events',                            11),
    ('delivery',      'Delivery',                4,  'Delivery',                          12),
    ('household',     'Household',               5,  'Household',                         1),
    ('office',        'Office',                  6,  'Office',                            7),
    ('restaurant',    'Restaurant / Cafe',       7,  'Restaurant / Cafe',                 13),
    ('hotel',         'Hotel / Guest House',     8,  'Hotel / Guest House',               14),
    ('catering',      'Catering',                9,  'Catering',                          15),
    ('grocery',       'Grocery / Kirana Store',  10, 'Grocery / Kirana Store',            16),
    ('supermarket',   'Supermarket / Mall',      11, 'Supermarket / Mall',                17),
    ('warehouse',     'Warehouse / Logistics',   12, 'Warehouse / Logistics',             18),
    ('manufacturing', 'Factory / Manufacturing', 13, 'Factory / Manufacturing',           19),
    ('construction',  'Construction',            14, 'Construction',                      20),
    ('real-estate',   'Real Estate / Society',   15, 'Real Estate / Property Management', 21),
    ('healthcare',    'Hospital / Clinic',       16, 'Hospital / Clinic',                 22),
    ('education',     'School / Coaching',       17, 'School / Coaching',                 23),
    ('salon',         'Salon / Spa',             18, 'Salon / Spa',                       25),
    ('gym',           'Gym / Fitness',           19, 'Gym / Fitness Center',              26),
    ('cleaning',      'Cleaning / Facility',     20, 'Cleaning / Facility Management',    27),
    ('security',      'Security Services',       21, 'Security Services',                 28),
    ('automobile',    'Automobile / Garage',     22, 'Automobile / Garage',               29),
    ('car-wash',      'Car Wash',                23, 'Car Wash',                          30),
    ('laundry',       'Laundry / Dry Clean',     24, 'Laundry / Dry Cleaning',            31),
    ('bakery',        'Bakery / Sweet Shop',     25, 'Bakery / Sweet Shop',               32),
    ('pharmacy',      'Pharmacy',                26, 'Pharmacy',                          33),
    ('ecommerce',     'E-commerce',              27, 'E-commerce',                        34),
    ('agriculture',   'Farm / Agriculture',      28, 'Farm / Agriculture',                35),
    ('wedding',       'Wedding / Banquet Hall',  29, 'Wedding / Banquet Hall',            36)
) AS v(slug, old_name, old_sort, new_name, new_sort)
WHERE bt.slug = v.slug AND bt.name = v.old_name AND bt.sort_order = v.old_sort;

-- Entities that only carry the legacy work-category get the Business / Work type of the same slug.
UPDATE business_profiles bp
SET business_type_id = bt.id, updated_at = now()
FROM work_categories wc
JOIN business_types bt ON bt.slug = wc.slug
WHERE bp.business_type_id IS NULL AND bp.category_id = wc.id;

-- Profiles that predate multi-select keep their single type as the primary chip.
INSERT INTO business_profile_types (business_profile_id, business_type_id, position)
SELECT bp.id, bp.business_type_id, 0
FROM business_profiles bp
WHERE bp.business_type_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM business_profile_types t WHERE t.business_profile_id = bp.id)
ON CONFLICT DO NOTHING;

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

UPDATE faq_entries
SET slug = left(trim(BOTH '-' FROM lower(regexp_replace(question, '[^a-zA-Z0-9]+', '-', 'g'))), 64)
WHERE slug IS NULL;
