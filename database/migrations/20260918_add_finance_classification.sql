-- Additive classification. Original bank rows and review history are never rewritten.
BEGIN;
SET LOCAL lock_timeout='2s';
CREATE TABLE finance.finance_transaction_types (
 code text PRIMARY KEY, name text NOT NULL,
 counts_as_expense boolean NOT NULL DEFAULT false, counts_as_income boolean NOT NULL DEFAULT false
);
INSERT INTO finance.finance_transaction_types VALUES
 ('INCOME','Inkomsten',false,true),('EXPENSE','Uitgaven',true,false),
 ('TRANSFER','Eigen overboeking',false,false),('SAVING','Sparen',false,false),
 ('INVESTMENT','Beleggen',false,false),('DEBT','Lening / aflossing',false,false),
 ('TAX','Belasting',true,false),('CORRECTION','Correctie / terugboeking',false,false),
 ('UNKNOWN','Nog niet bepaald',false,false);
CREATE TABLE finance.finance_category_baseline AS SELECT code,label FROM finance.finance_categories;
DROP TRIGGER immutable ON finance.finance_categories;
ALTER TABLE finance.finance_categories RENAME COLUMN label TO name;
ALTER TABLE finance.finance_categories
 ADD COLUMN id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
 ADD COLUMN label text GENERATED ALWAYS AS (name) STORED,
 ADD COLUMN parent_id uuid REFERENCES finance.finance_categories(id),
 ADD COLUMN transaction_type text NOT NULL DEFAULT 'UNKNOWN' REFERENCES finance.finance_transaction_types(code),
 ADD COLUMN active boolean NOT NULL DEFAULT true,
 ADD COLUMN sort_order integer NOT NULL DEFAULT 0,
 ADD COLUMN is_system boolean NOT NULL DEFAULT false,
 ADD COLUMN created_at timestamptz NOT NULL DEFAULT now(),
 ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now(),
 ADD CONSTRAINT finance_category_not_self CHECK(parent_id IS DISTINCT FROM id),
 ADD CONSTRAINT finance_category_name CHECK(length(btrim(name)) BETWEEN 1 AND 120);
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('inkomen','Inkomsten','INCOME',0,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'inkomen_salaris','Salaris',id,'INCOME',0,true FROM finance.finance_categories WHERE code='inkomen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'inkomen_uitkering','Uitkering',id,'INCOME',1,true FROM finance.finance_categories WHERE code='inkomen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'inkomen_omzet','Omzet',id,'INCOME',2,true FROM finance.finance_categories WHERE code='inkomen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'inkomen_freelance','Freelance',id,'INCOME',3,true FROM finance.finance_categories WHERE code='inkomen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'inkomen_rente','Rente',id,'INCOME',4,true FROM finance.finance_categories WHERE code='inkomen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'inkomen_dividend','Dividend',id,'INCOME',5,true FROM finance.finance_categories WHERE code='inkomen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'inkomen_teruggave','Teruggave',id,'INCOME',6,true FROM finance.finance_categories WHERE code='inkomen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'inkomen_verkoop','Verkoop',id,'INCOME',7,true FROM finance.finance_categories WHERE code='inkomen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'inkomen_overige_inkomsten','Overige inkomsten',id,'INCOME',8,true FROM finance.finance_categories WHERE code='inkomen';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('wonen','Wonen','EXPENSE',1,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'wonen_hypotheek_huur','Hypotheek/huur',id,'EXPENSE',0,true FROM finance.finance_categories WHERE code='wonen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'wonen_vve','VvE',id,'EXPENSE',1,true FROM finance.finance_categories WHERE code='wonen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'wonen_energie','Energie',id,'EXPENSE',2,true FROM finance.finance_categories WHERE code='wonen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'wonen_water','Water',id,'EXPENSE',3,true FROM finance.finance_categories WHERE code='wonen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'wonen_gemeentelijke_belastingen','Gemeentelijke belastingen',id,'TAX',4,true FROM finance.finance_categories WHERE code='wonen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'wonen_onderhoud','Onderhoud',id,'EXPENSE',5,true FROM finance.finance_categories WHERE code='wonen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'wonen_verbouwing','Verbouwing',id,'EXPENSE',6,true FROM finance.finance_categories WHERE code='wonen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'wonen_woonverzekering','Woonverzekering',id,'EXPENSE',7,true FROM finance.finance_categories WHERE code='wonen';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('boodschappen','Boodschappen & huishouden','EXPENSE',2,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'boodschappen_supermarkt','Supermarkt',id,'EXPENSE',0,true FROM finance.finance_categories WHERE code='boodschappen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'boodschappen_drogist','Drogist',id,'EXPENSE',1,true FROM finance.finance_categories WHERE code='boodschappen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'boodschappen_huishoudartikelen','Huishoudartikelen',id,'EXPENSE',2,true FROM finance.finance_categories WHERE code='boodschappen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'boodschappen_persoonlijke_verzorging','Persoonlijke verzorging',id,'EXPENSE',3,true FROM finance.finance_categories WHERE code='boodschappen';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('eten_drinken','Eten & drinken','EXPENSE',3,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'eten_drinken_restaurant','Restaurant',id,'EXPENSE',0,true FROM finance.finance_categories WHERE code='eten_drinken';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'eten_drinken_afhalen_bezorgen','Afhalen/bezorgen',id,'EXPENSE',1,true FROM finance.finance_categories WHERE code='eten_drinken';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'eten_drinken_cafe_bar','Cafe/bar',id,'EXPENSE',2,true FROM finance.finance_categories WHERE code='eten_drinken';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'eten_drinken_koffie_lunch','Koffie/lunch',id,'EXPENSE',3,true FROM finance.finance_categories WHERE code='eten_drinken';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('vervoer','Vervoer','EXPENSE',4,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vervoer_lease','Lease',id,'EXPENSE',0,true FROM finance.finance_categories WHERE code='vervoer';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vervoer_brandstof','Brandstof',id,'EXPENSE',1,true FROM finance.finance_categories WHERE code='vervoer';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vervoer_laden','Laden',id,'EXPENSE',2,true FROM finance.finance_categories WHERE code='vervoer';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vervoer_parkeren','Parkeren',id,'EXPENSE',3,true FROM finance.finance_categories WHERE code='vervoer';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vervoer_openbaar_vervoer','Openbaar vervoer',id,'EXPENSE',4,true FROM finance.finance_categories WHERE code='vervoer';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vervoer_taxi','Taxi',id,'EXPENSE',5,true FROM finance.finance_categories WHERE code='vervoer';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vervoer_fiets','Fiets',id,'EXPENSE',6,true FROM finance.finance_categories WHERE code='vervoer';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vervoer_onderhoud','Onderhoud',id,'EXPENSE',7,true FROM finance.finance_categories WHERE code='vervoer';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vervoer_verzekering','Verzekering',id,'EXPENSE',8,true FROM finance.finance_categories WHERE code='vervoer';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vervoer_wegenbelasting','Wegenbelasting',id,'TAX',9,true FROM finance.finance_categories WHERE code='vervoer';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('verzekeringen','Verzekeringen','EXPENSE',5,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'verzekeringen_zorgverzekering','Zorgverzekering',id,'EXPENSE',0,true FROM finance.finance_categories WHERE code='verzekeringen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'verzekeringen_aansprakelijkheid','Aansprakelijkheid',id,'EXPENSE',1,true FROM finance.finance_categories WHERE code='verzekeringen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'verzekeringen_rechtsbijstand','Rechtsbijstand',id,'EXPENSE',2,true FROM finance.finance_categories WHERE code='verzekeringen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'verzekeringen_reisverzekering','Reisverzekering',id,'EXPENSE',3,true FROM finance.finance_categories WHERE code='verzekeringen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'verzekeringen_overige','Overige',id,'EXPENSE',4,true FROM finance.finance_categories WHERE code='verzekeringen';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('gezondheid','Gezondheid','EXPENSE',6,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'gezondheid_tandarts','Tandarts',id,'EXPENSE',0,true FROM finance.finance_categories WHERE code='gezondheid';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'gezondheid_huisarts','Huisarts',id,'EXPENSE',1,true FROM finance.finance_categories WHERE code='gezondheid';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'gezondheid_medicijnen','Medicijnen',id,'EXPENSE',2,true FROM finance.finance_categories WHERE code='gezondheid';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'gezondheid_fysiotherapie','Fysiotherapie',id,'EXPENSE',3,true FROM finance.finance_categories WHERE code='gezondheid';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'gezondheid_bril_lenzen','Bril/lenzen',id,'EXPENSE',4,true FROM finance.finance_categories WHERE code='gezondheid';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'gezondheid_overige_zorg','Overige zorg',id,'EXPENSE',5,true FROM finance.finance_categories WHERE code='gezondheid';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('abonnementen','Abonnementen','EXPENSE',7,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'abonnementen_telefoon','Telefoon',id,'EXPENSE',0,true FROM finance.finance_categories WHERE code='abonnementen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'abonnementen_internet','Internet',id,'EXPENSE',1,true FROM finance.finance_categories WHERE code='abonnementen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'abonnementen_streaming','Streaming',id,'EXPENSE',2,true FROM finance.finance_categories WHERE code='abonnementen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'abonnementen_software','Software',id,'EXPENSE',3,true FROM finance.finance_categories WHERE code='abonnementen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'abonnementen_cloud','Cloud',id,'EXPENSE',4,true FROM finance.finance_categories WHERE code='abonnementen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'abonnementen_nieuws_media','Nieuws/media',id,'EXPENSE',5,true FROM finance.finance_categories WHERE code='abonnementen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'abonnementen_overige_abonnementen','Overige abonnementen',id,'EXPENSE',6,true FROM finance.finance_categories WHERE code='abonnementen';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('vrije_tijd','Vrije tijd','EXPENSE',8,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vrije_tijd_sport','Sport',id,'EXPENSE',0,true FROM finance.finance_categories WHERE code='vrije_tijd';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vrije_tijd_uitgaan','Uitgaan',id,'EXPENSE',1,true FROM finance.finance_categories WHERE code='vrije_tijd';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vrije_tijd_hobby','Hobby',id,'EXPENSE',2,true FROM finance.finance_categories WHERE code='vrije_tijd';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vrije_tijd_games','Games',id,'EXPENSE',3,true FROM finance.finance_categories WHERE code='vrije_tijd';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vrije_tijd_evenementen','Evenementen',id,'EXPENSE',4,true FROM finance.finance_categories WHERE code='vrije_tijd';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vrije_tijd_wellness','Wellness',id,'EXPENSE',5,true FROM finance.finance_categories WHERE code='vrije_tijd';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('vakantie','Vakantie & reizen','EXPENSE',9,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vakantie_accommodatie','Accommodatie',id,'EXPENSE',0,true FROM finance.finance_categories WHERE code='vakantie';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vakantie_vervoer','Vervoer',id,'EXPENSE',1,true FROM finance.finance_categories WHERE code='vakantie';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vakantie_vluchten','Vluchten',id,'EXPENSE',2,true FROM finance.finance_categories WHERE code='vakantie';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vakantie_autohuur','Autohuur',id,'EXPENSE',3,true FROM finance.finance_categories WHERE code='vakantie';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vakantie_activiteiten','Activiteiten',id,'EXPENSE',4,true FROM finance.finance_categories WHERE code='vakantie';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'vakantie_eten_drinken','Eten/drinken',id,'EXPENSE',5,true FROM finance.finance_categories WHERE code='vakantie';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('kleding','Kleding','EXPENSE',10,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'kleding_kleding','Kleding',id,'EXPENSE',0,true FROM finance.finance_categories WHERE code='kleding';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'kleding_schoenen','Schoenen',id,'EXPENSE',1,true FROM finance.finance_categories WHERE code='kleding';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'kleding_accessoires','Accessoires',id,'EXPENSE',2,true FROM finance.finance_categories WHERE code='kleding';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('gezin','Kinderen/gezin','EXPENSE',11,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'gezin_school_opleiding','School/opleiding',id,'EXPENSE',0,true FROM finance.finance_categories WHERE code='gezin';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'gezin_kleding','Kleding',id,'EXPENSE',1,true FROM finance.finance_categories WHERE code='gezin';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'gezin_zakgeld','Zakgeld',id,'EXPENSE',2,true FROM finance.finance_categories WHERE code='gezin';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'gezin_sport','Sport',id,'EXPENSE',3,true FROM finance.finance_categories WHERE code='gezin';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'gezin_zorg','Zorg',id,'EXPENSE',4,true FROM finance.finance_categories WHERE code='gezin';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'gezin_overige','Overige',id,'EXPENSE',5,true FROM finance.finance_categories WHERE code='gezin';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('financieel','Financieel','EXPENSE',12,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'financieel_bankkosten','Bankkosten',id,'EXPENSE',0,true FROM finance.finance_categories WHERE code='financieel';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'financieel_creditcardkosten','Creditcardkosten',id,'EXPENSE',1,true FROM finance.finance_categories WHERE code='financieel';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'financieel_rente','Rente',id,'EXPENSE',2,true FROM finance.finance_categories WHERE code='financieel';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'financieel_leningen','Leningen',id,'DEBT',3,true FROM finance.finance_categories WHERE code='financieel';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'financieel_aflossingen','Aflossingen',id,'DEBT',4,true FROM finance.finance_categories WHERE code='financieel';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'financieel_belastingen','Belastingen',id,'TAX',5,true FROM finance.finance_categories WHERE code='financieel';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('sparen_beleggen','Sparen & beleggen','SAVING',13,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'sparen_beleggen_sparen','Sparen',id,'SAVING',0,true FROM finance.finance_categories WHERE code='sparen_beleggen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'sparen_beleggen_beleggingen','Beleggingen',id,'INVESTMENT',1,true FROM finance.finance_categories WHERE code='sparen_beleggen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'sparen_beleggen_pensioen','Pensioen',id,'INVESTMENT',2,true FROM finance.finance_categories WHERE code='sparen_beleggen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'sparen_beleggen_crypto','Crypto',id,'INVESTMENT',3,true FROM finance.finance_categories WHERE code='sparen_beleggen';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('overboekingen','Overboekingen','TRANSFER',14,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'overboekingen_eigen_rekening','Eigen rekening',id,'TRANSFER',0,true FROM finance.finance_categories WHERE code='overboekingen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'overboekingen_spaarrekening','Spaarrekening',id,'TRANSFER',1,true FROM finance.finance_categories WHERE code='overboekingen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'overboekingen_gezamenlijke_rekening','Gezamenlijke rekening',id,'TRANSFER',2,true FROM finance.finance_categories WHERE code='overboekingen';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'overboekingen_creditcardbetaling','Creditcardbetaling',id,'TRANSFER',3,true FROM finance.finance_categories WHERE code='overboekingen';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('giften','Giften & cadeaus','EXPENSE',15,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'giften_cadeaus','Cadeaus',id,'EXPENSE',0,true FROM finance.finance_categories WHERE code='giften';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'giften_goede_doelen','Goede doelen',id,'EXPENSE',1,true FROM finance.finance_categories WHERE code='giften';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'giften_donaties','Donaties',id,'EXPENSE',2,true FROM finance.finance_categories WHERE code='giften';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('zakelijk','Zakelijk','EXPENSE',16,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'zakelijk_software','Software',id,'EXPENSE',0,true FROM finance.finance_categories WHERE code='zakelijk';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'zakelijk_hardware','Hardware',id,'EXPENSE',1,true FROM finance.finance_categories WHERE code='zakelijk';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'zakelijk_hosting_cloud','Hosting/cloud',id,'EXPENSE',2,true FROM finance.finance_categories WHERE code='zakelijk';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'zakelijk_kantoor','Kantoor',id,'EXPENSE',3,true FROM finance.finance_categories WHERE code='zakelijk';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'zakelijk_opleiding','Opleiding',id,'EXPENSE',4,true FROM finance.finance_categories WHERE code='zakelijk';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'zakelijk_reiskosten','Reiskosten',id,'EXPENSE',5,true FROM finance.finance_categories WHERE code='zakelijk';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'zakelijk_marketing','Marketing',id,'EXPENSE',6,true FROM finance.finance_categories WHERE code='zakelijk';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'zakelijk_administratie','Administratie',id,'EXPENSE',7,true FROM finance.finance_categories WHERE code='zakelijk';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'zakelijk_overige_bedrijfskosten','Overige bedrijfskosten',id,'EXPENSE',8,true FROM finance.finance_categories WHERE code='zakelijk';
INSERT INTO finance.finance_categories(code,name,transaction_type,sort_order,is_system) VALUES ('overig','Overig','UNKNOWN',17,true) ON CONFLICT(code) DO UPDATE SET transaction_type=EXCLUDED.transaction_type,sort_order=EXCLUDED.sort_order,is_system=true;
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'overig_onbekend','Onbekend',id,'UNKNOWN',0,true FROM finance.finance_categories WHERE code='overig';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'overig_eenmalig','Eenmalig',id,'UNKNOWN',1,true FROM finance.finance_categories WHERE code='overig';
INSERT INTO finance.finance_categories(code,name,parent_id,transaction_type,sort_order,is_system) SELECT 'overig_nog_classificeren','Nog classificeren',id,'UNKNOWN',2,true FROM finance.finance_categories WHERE code='overig';
CREATE TABLE finance.finance_category_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 category_id uuid NOT NULL REFERENCES finance.finance_categories(id),
 previous_data jsonb, new_data jsonb NOT NULL,
 actor text NOT NULL DEFAULT session_user, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION finance.category_change() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 -- Serialize taxonomy changes and classification to prevent reparenting races.
 PERFORM pg_advisory_xact_lock(hashtext('finance-category-learning'));
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'finance_category_deactivate_instead'; END IF;
 IF TG_OP='UPDATE' AND (NEW.id<>OLD.id OR NEW.code<>OLD.code OR NEW.created_at<>OLD.created_at) THEN
  RAISE EXCEPTION 'finance_category_identity_immutable'; END IF;
 IF NEW.parent_id IS NOT NULL AND (NOT EXISTS (
  SELECT 1 FROM finance.finance_categories WHERE id=NEW.parent_id AND parent_id IS NULL
 ) OR EXISTS(SELECT 1 FROM finance.finance_categories WHERE parent_id=NEW.id)) THEN
  RAISE EXCEPTION 'finance_category_two_levels_required'; END IF;
 NEW.updated_at=now();
 RETURN NEW;
END $$;
CREATE FUNCTION finance.category_audit() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$ BEGIN
 INSERT INTO finance.finance_category_events(category_id,previous_data,new_data)
 VALUES (NEW.id,CASE WHEN TG_OP='UPDATE' THEN to_jsonb(OLD) ELSE NULL END,to_jsonb(NEW));
 RETURN NEW;
END $$;
CREATE TRIGGER category_change BEFORE INSERT OR UPDATE OR DELETE ON finance.finance_categories
 FOR EACH ROW EXECUTE FUNCTION finance.category_change();
CREATE TRIGGER category_audit AFTER INSERT OR UPDATE ON finance.finance_categories
 FOR EACH ROW EXECUTE FUNCTION finance.category_audit();
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON finance.finance_category_events FOR EACH ROW EXECUTE FUNCTION finance.immutable();
CREATE TRIGGER no_truncate BEFORE TRUNCATE ON finance.finance_category_events FOR EACH STATEMENT EXECUTE FUNCTION finance.immutable();
ALTER TABLE finance.finance_review_events
 ADD COLUMN transaction_type text REFERENCES finance.finance_transaction_types(code),
 ADD COLUMN subcategory_code text REFERENCES finance.finance_categories(code),
 ADD COLUMN merchant_id uuid REFERENCES finance.finance_counterparties(id),
 ADD COLUMN classification_source text CHECK(classification_source IN ('RULE','MERCHANT','AI','MANUAL')),
 ADD COLUMN confidence numeric(5,4) CHECK(confidence BETWEEN 0 AND 1),
 ADD COLUMN confirmed boolean,
 ADD COLUMN model_version text,
 ADD COLUMN transfer_id uuid,
 ADD COLUMN linked_transaction_id uuid REFERENCES finance.finance_transactions(id),
 ADD COLUMN transfer_status text CHECK(transfer_status IN ('UNMATCHED','PROPOSED','CONFIRMED','REJECTED')),
 ADD CONSTRAINT finance_transfer_not_self CHECK(linked_transaction_id IS DISTINCT FROM transaction_id);
ALTER TABLE finance.finance_review_events DROP CONSTRAINT finance_suggestion_evidence,
 ADD CONSTRAINT finance_suggestion_evidence CHECK (
 (source_review_id IS NULL AND suggestion_method IS NULL) OR
 (source_review_id IS NOT NULL AND suggestion_method IS NOT NULL AND suggestion_method IN ('local-merchant-v1','local-merchant-v2')));
CREATE INDEX finance_review_current ON finance.finance_review_events(transaction_id,sequence_no DESC);
CREATE FUNCTION finance.validate_classification() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 PERFORM pg_advisory_xact_lock(hashtext('finance-category-learning'));
 IF NEW.subcategory_code IS NOT NULL AND NOT EXISTS (
   SELECT 1 FROM finance.finance_categories child JOIN finance.finance_categories parent ON parent.id=child.parent_id
   WHERE child.code=NEW.subcategory_code AND parent.code=NEW.category_code AND child.active AND parent.active
 ) THEN RAISE EXCEPTION 'finance_category_parent_mismatch'; END IF;
 IF NEW.category_code IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM finance.finance_categories WHERE code=NEW.category_code AND parent_id IS NULL AND active
 ) THEN RAISE EXCEPTION 'finance_category_inactive_or_not_root'; END IF;
 IF NEW.source_review_id IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM finance.finance_review_events s WHERE s.id=NEW.source_review_id
  AND coalesce(s.transaction_type,'UNKNOWN')=coalesce(NEW.transaction_type,'UNKNOWN')
  AND s.subcategory_code IS NOT DISTINCT FROM NEW.subcategory_code
  AND s.merchant_id IS NOT DISTINCT FROM NEW.merchant_id
 ) THEN RAISE EXCEPTION 'finance_classification_evidence_mismatch'; END IF;
 IF NEW.classification_source IN ('RULE','MERCHANT','AI') AND NEW.confirmed AND EXISTS (
  SELECT 1 FROM finance.finance_review_events r WHERE r.transaction_id=NEW.transaction_id AND coalesce(r.confirmed,true)
 ) THEN RAISE EXCEPTION 'finance_confirmed_classification_protected'; END IF;
 IF NEW.classification_source IS NOT NULL AND (NEW.transaction_type IS NULL OR NEW.confirmed IS NULL) THEN
  RAISE EXCEPTION 'finance_classification_incomplete'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER validate_classification BEFORE INSERT ON finance.finance_review_events
 FOR EACH ROW EXECUTE FUNCTION finance.validate_classification();
CREATE OR REPLACE VIEW finance.v_transactions AS
 SELECT t.*,review.category_code,review.id AS review_id,
 coalesce(review.transaction_type,'UNKNOWN') AS transaction_type,review.subcategory_code,review.merchant_id,
 coalesce(review.classification_source,CASE WHEN review.id IS NULL THEN NULL WHEN review.source_review_id IS NULL THEN 'MANUAL' ELSE 'MERCHANT' END) AS classification_source,
 review.confidence,coalesce(review.confirmed,review.id IS NOT NULL) AS confirmed,
 review.created_at AS classified_at,review.suggestion_method AS rule_version,review.model_version,
 review.source_review_id AS rule_review_id,review.transfer_id,review.linked_transaction_id,
 coalesce(review.transfer_status,'UNMATCHED') AS transfer_status,merchant.private_data AS merchant_data,
 (review.id IS NOT NULL AND review.transaction_type IS NULL) AS legacy_classification
 FROM finance.finance_transactions t
 LEFT JOIN LATERAL (SELECT * FROM finance.finance_review_events WHERE transaction_id=t.id
   AND coalesce(confirmed,true) ORDER BY sequence_no DESC LIMIT 1) review ON true
 LEFT JOIN finance.finance_counterparties merchant ON merchant.id=review.merchant_id
 WHERE EXISTS(SELECT 1 FROM finance.finance_transaction_sources s JOIN finance.finance_import_records r ON r.id=s.record_id
 JOIN finance.v_import_status b ON b.id=r.batch_id WHERE s.transaction_id=t.id AND b.status IN ('imported','partial'));
GRANT SELECT ON finance.finance_transaction_types,finance.finance_category_events TO core_finance_api,core_finance_ingest;
GRANT INSERT ON finance.finance_counterparties TO core_finance_api;
REVOKE ALL ON FUNCTION finance.category_change(),finance.category_audit(),finance.validate_classification() FROM PUBLIC;
COMMIT;
