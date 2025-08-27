# DUMMY DATA - AUTOMATION PROJECT

## Περιεχόμενα

Αυτός ο φάκελος περιέχει όλα τα dummy data που χρειάζονται για την εργασία αυτοματισμού.

### Δομή Φακέλων

```
dummy_data/
├── forms/          # 5 HTML φόρμες με στοιχεία πελατών
├── emails/         # 10 email αρχεία (.eml format)
├── invoices/       # 10 HTML τιμολόγια (simulacra για PDF)
├── templates/      # Template για την οργάνωση δεδομένων
└── README.md       # Αυτό το αρχείο
```

### Λεπτομέρειες

#### Forms (5 αρχεία)
- **contact_form_1.html** - Digital Marketing Pro (Νίκος Παπαδόπουλος)
- **contact_form_2.html** - Δικηγορικό Γραφείο (Μαρία Κώστα)
- **contact_form_3.html** - Restaurant Chain (Γιάννης Αντωνίου)
- **contact_form_4.html** - Κέντρο Υγείας (Άννα Γεωργίου)
- **contact_form_5.html** - Κατασκευές (Κώστας Δημητρίου)

**Στοιχεία για εξαγωγή:**
- Όνομα και Επώνυμο
- Email
- Τηλέφωνο
- Εταιρεία
- Υπηρεσία Ενδιαφέροντος
- Μήνυμα
- Προτεραιότητα
- Ημερομηνία Υποβολής

#### Emails (10 αρχεία)
- **email_01.eml** - TechCorp AE (Σπύρος Μιχαήλ) - CRM System
- **email_02.eml** - Fashion Store (Ελένη Παπαγεωργίου) - E-commerce
- **email_03.eml** - Τιμολόγιο #TF-2024-001 (Office Supplies)
- **email_04.eml** - AutoService (Παναγιώτης Κωνσταντίνου) - Garage Management
- **email_05.eml** - Τιμολόγιο #TF-2024-002 (Software Licenses)
- **email_06.eml** - Hotel Group (Δημήτρης Βασιλείου) - Hotel Management
- **email_07.eml** - Τιμολόγιο #TF-2024-003 (Hardware Equipment)
- **email_08.eml** - PharmNet (Βασίλης Γεωργάκης) - Pharmacy System
- **email_09.eml** - Τιμολόγιο #TF-2024-004 (Marketing Services)
- **email_10.eml** - GreenFood Delivery (Σοφία Αλεξάνδρου) - Food Delivery App

**Τύποι emails:**
- Client inquiries (60%)
- Invoice notifications (40%)

#### Invoices (10 αρχεία HTML)
- **TF-2024-001** - Office Supplies (€1,054.00)
- **TF-2024-002** - Software Licenses (€2,976.00)
- **TF-2024-003** - Hardware Equipment (€5,208.00)
- **TF-2024-004** - Marketing Services (€1,984.00)
- **TF-2024-005** - POS Equipment (€2,517.20)
- **TF-2024-006** - Development Services (€7,712.80)
- **TF-2024-007** - Network Equipment (€2,132.80)
- **TF-2024-008** - Legal Tech Setup (€4,712.00)
- **TF-2024-009** - Gym Management SaaS (€1,971.60)
- **TF-2024-010** - Photography Website (€4,340.00)

**Στοιχεία για εξαγωγή:**
- Αριθμός Τιμολογίου
- Ημερομηνία
- Όνομα Πελάτη
- Καθαρή Αξία
- ΦΠΑ (24%)
- Συνολικό Ποσό
- Περιγραφή Προϊόντων/Υπηρεσιών

### Template
- **data_extraction_template.csv** - Προτεινόμενη δομή για την οργάνωση των εξαχθέντων δεδομένων

### Σημειώσεις για Υλοποίηση

1. **Encoding**: Όλα τα αρχεία είναι σε UTF-8 για σωστή υποστήριξη ελληνικών χαρακτήρων
2. **Formats**:
   - Forms: HTML
   - Emails: EML (plain text με headers)
   - Invoices: HTML (εύκολα parseable)
3. **Realism**: Τα δεδομένα είναι realistic και αντιπροσωπευτικά πραγματικών business scenarios
4. **Diversity**: Διαφορετικοί τύποι επιχειρήσεων, ποσά, και services

### Testing Strategy

Προτείνουμε τα εξής test cases:
- Εξαγωγή πλήρων στοιχείων από κάθε τύπο αρχείου
- Handling ελληνικών χαρακτήρων
- Parsing διαφορετικών formats (HTML, EML)
- Έλεγχος ακρίβειας αριθμητικών τιμών
- Error handling για μη-έγκυρα αρχεία

**Καλή επιτυχία στην υλοποίηση!**
