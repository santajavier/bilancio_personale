import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import plotly.express as px  # <--- AGGIUNGI QUESTA RIGA

# --- CONFIGURAZIONE PAGINA ---
titolo = st.secrets["config"].get("TITOLO_APP", "Le Mie Finanze")
st.set_page_config(page_title=titolo, page_icon="📊", layout="centered")

# --- SCHERMATA DI LOGIN ---
if "autenticato" not in st.session_state:
    st.session_state["autenticato"] = False

if not st.session_state["autenticato"]:
    st.title("🔒 Accesso Richiesto")
    pwd_inserita = st.text_input("Inserisci la password", type="password")
    if st.button("Accedi"):
        if pwd_inserita == st.secrets["config"]["PASSWORD_ACCESSO"] or pwd_inserita == st.secrets["config"]["MASTER_PASSWORD"]:
            st.session_state["autenticato"] = True
            st.rerun()
        else:
            st.error("❌ Password errata!")
    st.stop() # Blocca l'esecuzione del resto del codice se non sei autenticato

st.title(f"💸 {titolo} - Nuova Transazione")

# --- 1. CONNESSIONE A GOOGLE SHEETS ---
@st.cache_resource
def connetti_gsheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(st.secrets["connections"]["gsheets"], scopes=scopes)
    client = gspread.authorize(creds)
    
    # Apriamo il foglio tramite l'URL salvato nei secrets
    foglio_google = client.open_by_url(st.secrets["config"]["URL_FOGLIO"])
    return foglio_google

foglio = connetti_gsheets()

# Connessione ai tre tab specifici
tab_elenchi = foglio.worksheet("Elenchi")
tab_storico = foglio.worksheet("Storico") 
tab_tipologie = foglio.worksheet("Tipologie") # <--- AGGIUNTO!

# --- LETTURA DINAMICA DELLE CATEGORIE E TIPOLOGIE ---
@st.cache_data(ttl=600) 
def carica_elenchi():
    dati = tab_elenchi.get_all_records()
    return pd.DataFrame(dati)

@st.cache_data(ttl=600)
def carica_tipologie():
    dati = tab_tipologie.get_all_records()
    df = pd.DataFrame(dati)
    if df.empty: return ["Contanti"] # Fallback di sicurezza
    df.columns = [c.strip().lower() for c in df.columns]
    if "tipologia" in df.columns:
        return [t for t in df["tipologia"].dropna().unique().tolist() if str(t).strip()]
    return ["Contanti"]

try:
    df_elenchi = carica_elenchi()
    lista_tipologie = carica_tipologie() # <--- ORA È DINAMICA!
except Exception as e:
    st.error(f"Errore nella lettura dei tab. Dettaglio: {e}")
    st.stop()

lista_flussi_dinamici = df_elenchi["Flusso"].dropna().unique().tolist() if not df_elenchi.empty else ["Pagamento", "Incasso", "Giroconto"]

# --- MENU LATERALE (SIDEBAR) ---
st.sidebar.title("Navigazione")
pagina_scelta = st.sidebar.radio("Vai a:", [
    "💸 Nuova Transazione", 
    "📊 Dashboard Statistiche", 
    "🤝 Gestione Prestiti", 
    "📝 Registro Transazioni",
    "⚙️ Impostazioni" # <--- AGGIUNTO!
])

st.sidebar.divider()
if st.sidebar.button("🚪 Esci"):
    st.session_state["autenticato"] = False
    st.rerun()

# --- LETTURA DINAMICA DELLE CATEGORIE ---
# ... (lascia intatto il blocco carica_elenchi che hai già) ...

@st.cache_data(ttl=60)
def carica_storico():
    dati = tab_storico.get_all_records()
    df_caricato = pd.DataFrame(dati)
    if df_caricato.empty:
        return pd.DataFrame()
        
    df_caricato["gs_row"] = df_caricato.index + 2
    df_caricato.columns = df_caricato.columns.astype(str).str.strip().str.lower()
    
    # --- PULIZIA AGGRESSIVA DEI NUMERI ---
    for col in ["uscite", "entrate", "giroconti", "importo"]:
        if col in df_caricato.columns:
            # 1. Convertiamo in stringa
            # 2. Rimuoviamo tutto ciò che NON è numero, virgola o punto (es. rimuove '€', ' ', 'kg', ecc)
            # 3. Sostituiamo la virgola col punto
            serie = df_caricato[col].astype(str).str.replace(r'[^\d,.-]', '', regex=True)
            serie = serie.str.replace(",", ".", regex=False)
            
            # 4. Convertiamo in numerico forzato
            df_caricato[col] = pd.to_numeric(serie, errors="coerce").fillna(0.0)
        else:
            df_caricato[col] = 0.0
            
    if "data" in df_caricato.columns:
        df_caricato["data_dt"] = pd.to_datetime(df_caricato["data"], format="%d/%m/%Y", errors="coerce")
        
    return df_caricato

# ==========================================
#      PAGINA 1: INSERIMENTO SPESE
# ==========================================
if pagina_scelta == "💸 Nuova Transazione":
    st.title("Bilancio Personale")
    st.subheader("💸 Nuova Transazione")
    
    # 💡 ABBIAMO AGGIUNTO LA KEY UNICA PER RISOLVERE L'ERRORE
    flusso_input = st.selectbox("🔄 Che operazione devi fare?", lista_flussi_dinamici, key="sel_flusso")
    
    df_filtrato = df_elenchi[df_elenchi["Flusso"] == flusso_input]
    sotto_categorie_disponibili = df_filtrato["Sotto categoria"].dropna().tolist()

    col1, col2 = st.columns(2)

    # FUNZIONE SICURA PER LA CONVERSIONE NUMERICA (Gestisce virgole e punti)
    def converte_numero(testo):
        if not testo: return 0.0
        # Rimuoviamo il simbolo dell'euro e spazi
        t = str(testo).replace("€", "").strip()
        # Se l'utente usa la virgola come decimale (es. 3,49 o 3.49)
        if "," in t and "." in t:
            # Caso in cui ci sono entrambi (es. 1.234,56)
            t = t.replace(".", "").replace(",", ".")
        elif "," in t:
            t = t.replace(",", ".")
        try:
            return float(t)
        except ValueError:
            return 0.0

    with col1:
            data_input = st.date_input("📅 Data", datetime.today(), key="input_data")
            importo_str = st.text_input("💶 Importo Totale Pagato (€)", value="0.00", key="input_importo")
            importo_digitato = converte_numero(importo_str)
            
            if flusso_input == "Giroconto":
                conto_partenza = st.selectbox("📤 Da quale conto escono?", lista_tipologie, key="sel_conto_out")
            else:
                tipologia_input = st.selectbox("💳 Conto o Carta", lista_tipologie, key="sel_conto_in")

    with col2:
        if flusso_input == "Giroconto":
            conto_destinazione = st.selectbox("📥 In quale conto entrano?", lista_tipologie, key="sel_conto_dest")
            descrizione_input = st.text_input("📝 Descrizione", value="Giroconto / Prelievo", key="input_desc_giro")
            st.info("💡 Verranno create due righe bilanciate.")
        else:
            sottocat_input = st.selectbox("📂 Sotto Categoria", sotto_categorie_disponibili, key="sel_sottocat")
            descrizione_input = st.text_input("📝 Descrizione", key="input_desc_normale")
            
            if sottocat_input:
                categoria_auto = df_filtrato[df_filtrato["Sotto categoria"] == sottocat_input]["Categoria"].values[0]
                st.info(f"Categoria assegnata: **{categoria_auto}**")

    st.write("") 
    
    # --- LOGICA SPESA CONDIVISA DINAMICA (STILE SPLITWISE) ---
    spesa_condivisa = False
    quote_altri = {}
    quota_mia = 0.0
    
    if flusso_input == "Pagamento":
        st.divider()
        spesa_condivisa = st.checkbox("🤝 Condividi questa spesa con altre persone")
        
        if spesa_condivisa:
            # 1. Recupero rubrica dallo storico
            df_storico = carica_storico()
            persone_note = []
            if not df_storico.empty:
                cat_prestiti = ["prestiti", "rientro prestiti"]
                df_prestiti_temp = df_storico[df_storico["categoria"].astype(str).str.lower().isin(cat_prestiti)]
                for sotto_cat in df_prestiti_temp["sotto categoria"].dropna().unique():
                    testo = str(sotto_cat).lower().strip()
                    if testo.startswith("prestito soldi "): persone_note.append(testo.replace("prestito soldi ", "").title())
                    elif testo.startswith("soldi "): persone_note.append(testo.replace("soldi ", "").title())
            
            persone_note = sorted(list(set(persone_note)))

            # 2. Selezione Partecipanti
            st.caption("Seleziona i partecipanti (tu sei incluso automaticamente nel calcolo).")
            col_s1, col_s2 = st.columns(2)
            
            with col_s1:
                persone_selezionate = st.multiselect("👥 Seleziona dalla rubrica:", options=persone_note)
            with col_s2:
                nuove_persone_str = st.text_input("✍️ O aggiungi nomi nuovi (separati da virgola):")
                
            nuove_persone = [p.strip().title() for p in nuove_persone_str.split(",") if p.strip()]
            tutte_le_persone = list(dict.fromkeys(persone_selezionate + nuove_persone))
            
            # 3. Metodo di divisione e quote
            if tutte_le_persone:
                st.write("💰 **Modalità di divisione:**")
                metodo_divisione = st.radio("Come vuoi dividere?", ["📊 In parti uguali", "✍️ Manualmente"], horizontal=True)
                
                if metodo_divisione == "📊 In parti uguali":
                    num_totale = len(tutte_le_persone) + 1 # +1 perché ci sei tu!
                    quota_base = round(importo_digitato / num_totale, 2)
                    
                    # Tu ti becchi la differenza esatta (così assorbi l'arrotondamento)
                    quota_mia = round(importo_digitato - (quota_base * len(tutte_le_persone)), 2)
                    
                    for persona in tutte_le_persone:
                        quote_altri[persona] = quota_base
                        
                    st.info(f"Ognuno dei {len(tutte_le_persone)} partecipanti paga **{quota_base:.2f} €**. La tua quota (arrotondata) è **{quota_mia:.2f} €**.")
                    
                else: # Manuale
                    st.write("Inserisci le quote esatte (puoi usare la virgola).")
                    
                    num_colonne = min(len(tutte_le_persone) + 1, 3)
                    col_quote = st.columns(num_colonne)
                    
                    with col_quote[0]:
                        q_mia_str = st.text_input("La TUA quota (€)", value="0.00", key="quota_mia_manuale")
                        quota_mia = converte_numero(q_mia_str)
                        
                    for idx, persona in enumerate(tutte_le_persone):
                        with col_quote[(idx + 1) % num_colonne]:
                            q_p_str = st.text_input(f"Quota {persona} (€)", value="0.00", key=f"quota_{persona}")
                            quota_p = converte_numero(q_p_str)
                            
                            if quota_p > 0:
                                quote_altri[persona] = quota_p

                    totale_inserito = quota_mia + sum(quote_altri.values())
                    differenza = importo_digitato - totale_inserito
                    
                    if abs(differenza) > 0.001:
                        st.warning(f"⚠️ Attenzione: la somma inserita ({totale_inserito:.2f} €) dista di {abs(differenza):.2f} € dal totale pagato!")
                    else:
                        st.success("✅ Le quote coincidono perfettamente con il totale pagato.")

    # TRASFORMATO IN PULSANTE NORMALE
    submit_btn = st.button("💾 Salva nel Database", use_container_width=True)

    # --- MOTORE DI SALVATAGGIO ---
    if submit_btn:
        permesso_zero = False
        if flusso_input != "Giroconto":
            voce_scelta = str(sottocat_input).lower().strip()
            # Consenti importi negativi o zero per azzeramenti e allineamenti
            if voce_scelta.startswith("azzeramento soldi") or voce_scelta == "saldo manuale" or flusso_input == "Allineamento patrimonio":
                permesso_zero = True

        errore_quote = False
        if spesa_condivisa and (abs((quota_mia + sum(quote_altri.values())) - importo_digitato) > 0.001):
            errore_quote = True

        if importo_digitato == 0 and not permesso_zero:
            st.warning("⚠️ Inserisci un importo diverso da zero (lo 0 è consentito solo per azzeramenti e saldi manuali)!")
        elif flusso_input == "Giroconto" and conto_partenza == conto_destinazione:
            st.warning("⚠️ Il conto di partenza e destinazione non possono essere uguali!")
        elif errore_quote:
            st.error("❌ Le quote inserite non corrispondono all'importo totale! Correggi la divisione prima di salvare.")
        else:
            anno_calc = data_input.year
            mese_calc = data_input.month
            righe_da_salvare = []
            
            if flusso_input == "Giroconto":
                righe_da_salvare = [
                    {"data": data_input.strftime("%d/%m/%Y"), "anno": anno_calc, "mese": mese_calc, "uscite": 0.0, "entrate": 0.0, "giroconti": -float(importo_digitato), "importo": -float(importo_digitato), "tipologia": conto_partenza, "sotto categoria": "giroconto in uscita", "descrizione": descrizione_input, "categoria": "giroconti", "flusso": "Giroconto"},
                    {"data": data_input.strftime("%d/%m/%Y"), "anno": anno_calc, "mese": mese_calc, "uscite": 0.0, "entrate": 0.0, "giroconti": float(importo_digitato), "importo": float(importo_digitato), "tipologia": conto_destinazione, "sotto categoria": "giroconto in entrata", "descrizione": descrizione_input, "categoria": "giroconti", "flusso": "Giroconto"}
                ]
            elif spesa_condivisa:
                # 1. TUA quota reale (forzata a float pulito)
                q_mia_pulita = round(float(quota_mia), 2)
                if q_mia_pulita > 0:
                    righe_da_salvare.append({
                        "data": data_input.strftime("%d/%m/%Y"), "anno": anno_calc, "mese": mese_calc, 
                        "uscite": q_mia_pulita, "entrate": 0.0, "giroconti": 0.0, "importo": -q_mia_pulita, 
                        "tipologia": tipologia_input, "sotto categoria": sottocat_input, 
                        "descrizione": descrizione_input, "categoria": categoria_auto, "flusso": "Pagamento"
                    })
                
                # 2. Quote degli altri (forzate a float pulito)
                for persona, quota in quote_altri.items():
                    q_altrui_pulita = round(float(quota), 2)
                    if q_altrui_pulita > 0:
                        righe_da_salvare.append({
                            "data": data_input.strftime("%d/%m/%Y"), "anno": anno_calc, "mese": mese_calc, 
                            "uscite": q_altrui_pulita, "entrate": 0.0, "giroconti": 0.0, "importo": -q_altrui_pulita, 
                            "tipologia": tipologia_input, "sotto categoria": f"prestito soldi {persona}", 
                            "descrizione": f"{descrizione_input} (Quota {persona})", "categoria": "prestiti", "flusso": "Pagamento"
                        })
            else:
                imp_pulito = round(float(importo_digitato), 2)
                
                # --- NUOVA LOGICA DEI FLUSSI ---
                uscite_calc, entrate_calc = 0.0, 0.0
                
                if flusso_input == "Pagamento":
                    uscite_calc = imp_pulito
                    importo_netto = -imp_pulito
                elif flusso_input == "Incasso":
                    entrate_calc = imp_pulito
                    importo_netto = imp_pulito
                elif flusso_input == "Allineamento saldo conto":
                    # L'allineamento non tocca uscite ed entrate (così non sballa i grafici)
                    importo_netto = imp_pulito
                elif flusso_input == "Allineamento saldo prestiti":
                    # L'allineamento non tocca uscite ed entrate (così non sballa i grafici)    
                    importo_netto = imp_pulito
                else:
                    importo_netto = 0.0
                
                righe_da_salvare = [{
                    "data": data_input.strftime("%d/%m/%Y"), "anno": anno_calc, "mese": mese_calc, 
                    "uscite": uscite_calc, "entrate": entrate_calc, "giroconti": 0.0, "importo": importo_netto, 
                    "tipologia": tipologia_input, "sotto categoria": sottocat_input, 
                    "descrizione": descrizione_input, "categoria": categoria_auto, "flusso": flusso_input
                }]

            # --- PREPARAZIONE DATI RIGOROSA ---
            ordine_colonne = ["data", "anno", "mese", "uscite", "entrate", "giroconti", "importo", "tipologia", "sotto categoria", "descrizione", "categoria", "flusso"]
            
            valori_da_scrivere = []
            for riga in righe_da_salvare:
                riga_formattata = []
                for col in ordine_colonne:
                    valore = riga.get(col, "")
                    # Se è un numero, lo forziamo a stringa con il punto decimale
                    if isinstance(valore, (int, float)):
                        riga_formattata.append(f"{valore:.2f}") 
                    else:
                        riga_formattata.append(str(valore))
                valori_da_scrivere.append(riga_formattata)

            try:
                # Usiamo RAW per evitare che Google Sheets applichi formati locali (es. virgole italiane)
                tab_storico.append_rows(valori_da_scrivere, value_input_option='RAW')
                st.success(f"✅ Registrazione completata!")
                st.cache_data.clear()
            except Exception as e:
                st.error(f"❌ Errore durante il salvataggio: {e}")
                                
# ==========================================
#      PAGINA 2: DASHBOARD STATISTICHE
# ==========================================
elif pagina_scelta == "📊 Dashboard Statistiche":
    st.title("Bilancio Personale")
    st.subheader("📊 Sala Comandi Finanziaria")

    df_storico = carica_storico()

    if df_storico.empty or "data_dt" not in df_storico.columns or df_storico["data_dt"].dropna().empty:
        st.info("ℹ️ Nessun dato valido trovato nel foglio 'Storico'. Inserisci almeno una transazione per generare i grafici!")
    else:
        # --- 0. FILTRI TEMPORALI GLOBALI ---
        st.sidebar.markdown("### 🗓️ Periodo di Analisi")
        min_data = df_storico["data_dt"].dropna().min().date()
        max_data = df_storico["data_dt"].dropna().max().date()
        
        data_inizio_default = datetime.today().replace(day=1).date()
        data_fine_default = datetime.today().date()
        
        if data_inizio_default < min_data: data_inizio_default = min_data
        if data_fine_default > max_data: data_fine_default = max_data

        data_inizio = st.sidebar.date_input("Data Inizio", data_inizio_default)
        data_fine = st.sidebar.date_input("Data Fine", data_fine_default)

        # Filtro periodo
        df_periodo = df_storico[(df_storico["data_dt"].dt.date >= data_inizio) & (df_storico["data_dt"].dt.date <= data_fine)]

        # --- SEZIONE 1: LIQUIDITÀ CONTI & DEBITI/CREDITI ---
        col_liq = st.columns(1)

        # --- SEZIONE 1: LIQUIDITÀ CONTI ---
        st.subheader("💳 Liquidità Attuale per Conto")
        
        saldi_attuali = {}
        conti_esistenti = df_storico["tipologia"].dropna().unique()
        
        for conto in conti_esistenti:
            if not str(conto).strip(): continue
            
            # Isolo tutte le transazioni di questo specifico conto
            df_conto = df_storico[df_storico["tipologia"] == conto]
            
            # Cerco se c'è un punto di salvataggio (saldo manuale)
            df_saldimanuali = df_conto[df_conto["sotto categoria"].astype(str).str.lower() == "saldo manuale"]
            
            if not df_saldimanuali.empty:
                # Prendo l'inserimento più recente
                ultima_rettifica = df_saldimanuali.sort_values(by="data_dt", ascending=False).iloc[0]
                data_rettifica = ultima_rettifica["data_dt"]
                saldo_base = ultima_rettifica["importo"]
                
                # Sommo solo i movimenti con data MAGGIORE rispetto al checkpoint
                df_successive = df_conto[(df_conto["data_dt"] > data_rettifica) & (df_conto["sotto categoria"].astype(str).str.lower() != "saldo manuale")]
                saldo_finale = saldo_base + df_successive["importo"].sum()
            else:
                # Nessun checkpoint trovato: sommo tutto lo storico normalmente
                saldo_finale = df_conto["importo"].sum()
                
            saldi_attuali[conto] = saldo_finale

        totale_patrimonio = sum(saldi_attuali.values())
        st.metric("Patrimonio Totale Tracciato", f"{totale_patrimonio:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
        
        for conto, saldo in saldi_attuali.items():
            st.write(f"- **{conto}**: `{saldo:,.2f} €`".replace(",", "X").replace(".", ",").replace("X", "."))
        
        st.divider()

        # --- SEZIONE 2: RISULTATO PERIODO (DOPPIA VISTA) ---
        st.subheader(f"📈 Risultato dal {data_inizio.strftime('%d/%m/%Y')} al {data_fine.strftime('%d/%m/%Y')}")
        
        # 1. Calcoli TOTALI (inclusi i prestiti, esclusi giroconti)
        df_senza_giroconti = df_periodo[df_periodo["flusso"].astype(str).str.lower() != "giroconto"]
        tot_entrate = df_senza_giroconti["entrate"].sum()
        tot_uscite = df_senza_giroconti["uscite"].sum()
        risultato_netto = tot_entrate - tot_uscite

        # 2. Calcoli REALI (esclusi prestiti, rientri e giroconti)
        cat_escluse = ["prestiti", "rientro prestiti"]
        df_reale = df_senza_giroconti[~df_senza_giroconti["categoria"].astype(str).str.lower().isin(cat_escluse)]
        tot_entrate_reali = df_reale["entrate"].sum()
        tot_uscite_reali = df_reale["uscite"].sum()
        risultato_netto_reale = tot_entrate_reali - tot_uscite_reali

        st.markdown("#### 🏦 Flusso di Cassa Globale (Include i prestiti)")
        m1, m2, m3 = st.columns(3)
        m1.metric("Totale Entrate", f"{tot_entrate:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
        m2.metric("Totale Uscite", f"{tot_uscite:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
        m3.metric("Bilancio", f"{risultato_netto:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))

        st.markdown("#### 🛒 Spese ed Entrate Effettive (Esclusi i prestiti)")
        r1, r2, r3 = st.columns(3)
        r1.metric("Entrate Reali", f"{tot_entrate_reali:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
        r2.metric("Uscite Reali", f"{tot_uscite_reali:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
        r3.metric("Bilancio Reale", f"{risultato_netto_reale:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))

        st.divider()

        # --- SEZIONE 3 & 4: SPESE CATEGORIA & USCITE CONTO ---
        col_cat, col_spese_conto = st.columns(2)
        df_solo_uscite = df_periodo[(df_periodo["uscite"] > 0) & (df_periodo["flusso"].astype(str).str.lower() != "giroconto")]

        with col_cat:
            st.subheader("🏷️ Spese per Categoria")
            if not df_solo_uscite.empty:
                # Prepariamo i dati per Plotly
                df_pie = df_solo_uscite.groupby("categoria")["uscite"].sum().reset_index()
                
                # Creiamo un bellissimo grafico a "ciambella" (hole=0.4 crea il buco al centro)
                fig = px.pie(
                    df_pie, 
                    values='uscite', 
                    names='categoria', 
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                
                # Nascondiamo la legenda esterna e mettiamo le etichette dentro le fette
                fig.update_traces(textposition='inside', textinfo='percent+label')
                fig.update_layout(margin=dict(t=10, b=10, l=0, r=0), showlegend=False)
                
                # Mostriamo il grafico in Streamlit
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Nessuna uscita nel periodo.")

        with col_spese_conto:
            st.subheader("💳 Uscite per Conto/Metodo")
            if not df_solo_uscite.empty:
                spese_per_conto = df_solo_uscite.groupby("tipologia")["uscite"].sum().sort_values(ascending=True)
                st.bar_chart(spese_per_conto, horizontal=True)
            else:
                st.info("Nessuna uscita nel periodo.")

        st.divider()

        # --- SEZIONE 5: TABELLA DETTAGLIATA ---
        st.subheader("📋 Elenco Dettagliato Movimenti")
        tutte_le_cat = ["Tutte"] + sorted([c for c in df_periodo["categoria"].dropna().unique().tolist() if str(c).strip()])
        cat_selezionata = st.selectbox("Filtra per Categoria:", tutte_le_cat)
        
        df_mostra = df_periodo.copy()
        if cat_selezionata != "Tutte":
            df_mostra = df_mostra[df_mostra["categoria"] == cat_selezionata]
            
        colonne_vista = [c for c in ["data", "flusso", "categoria", "sotto categoria", "descrizione", "tipologia", "importo"] if c in df_mostra.columns]
        st.dataframe(df_mostra.sort_values(by="data_dt", ascending=False)[colonne_vista], use_container_width=True)

# ==========================================
#       PAGINA 3: GESTIONE PRESTITI
# ==========================================
elif pagina_scelta == "🤝 Gestione Prestiti":
    st.title("Bilancio Personale")
    st.subheader("🤝 Gestione Debiti e Crediti")
    
    df_storico = carica_storico()
    
    if df_storico.empty:
        st.info("Nessun dato presente nel database.")
    else:
        # 1. FILTRO AMPLIATO E PRECISO SULLE CATEGORIE
        categorie_valide = ["prestiti", "rientro prestiti", "entrate varie"]
        # Usiamo strip() per evitare errori se hai inserito spazi alla fine tipo "rientro prestiti "
        condizione_cat = df_storico["categoria"].astype(str).str.lower().str.strip().isin(categorie_valide)
        
        df_prestiti = df_storico[condizione_cat].copy()

        if df_prestiti.empty:
            st.success("Nessun prestito registrato finora. Tutto in regola!")
        else:
            # 2. FUNZIONE ESTRAZIONE NOMI RIGOROSA
            def estrai_nome_persona(sotto_cat):
                testo = str(sotto_cat).lower().strip()
                
                # Accetta SOLO diciture esatte per evitare "soldi laurea" ecc.
                if testo.startswith("prestito soldi "):
                    return testo.replace("prestito soldi ", "", 1).strip().title()
                elif testo.startswith("soldi "):
                    return testo.replace("soldi ", "", 1).strip().title()
                elif "beni/servizi - soldi " in testo:
                    return testo.split("beni/servizi - soldi ")[-1].strip().title()
                elif testo.startswith("azzeramento prestiti "):
                    return testo.replace("azzeramento prestiti ", "", 1).strip().title()
                elif testo.startswith("azzeramento soldi "):
                    return testo.replace("azzeramento soldi ", "", 1).strip().title()
                
                # Se non è una delle frasi sopra, scarta la riga
                return "Sconosciuto"

            df_prestiti["persona"] = df_prestiti["sotto categoria"].apply(estrai_nome_persona)
            
            # Escludiamo le righe che non c'entrano coi prestiti (es. regali di laurea, soldi trovati)
            df_prestiti = df_prestiti[df_prestiti["persona"] != "Sconosciuto"]
            
            if df_prestiti.empty:
                st.info("Nessun movimento di prestito valido trovato.")
            else:
                # 3. MOTORE CALCOLO SEGNI (Affidato al Database)
                def calcola_variazione(row):
                    return float(row.get("importo", 0.0))

                df_prestiti["variazione_credito"] = df_prestiti.apply(calcola_variazione, axis=1)
                
                st.divider()
                
                # --- FILTRI DI ANALISI (TEMPO E ABBONAMENTI) ---
                st.markdown("### 🔍 Analisi Abbonamenti e Periodo")
                col_f1, col_f2 = st.columns(2)
                
                with col_f1:
                    min_date = df_prestiti["data_dt"].min().date()
                    max_date = df_prestiti["data_dt"].max().date()
                    filtro_date = st.date_input("Filtro Temporale:", value=(min_date, max_date), min_value=min_date, max_value=max_date)
                    
                with col_f2:
                    filtro_causale = st.text_input("Filtra per Abbonamento/Causale (es. 'spotify'):").strip().lower()

                # Applichiamo i filtri scelti dall'utente
                df_filtrato = df_prestiti.copy()
                
                if len(filtro_date) == 2:
                    start_date, end_date = filtro_date
                    df_filtrato = df_filtrato[(df_filtrato["data_dt"].dt.date >= start_date) & (df_filtrato["data_dt"].dt.date <= end_date)]
                    
                if filtro_causale:
                    df_filtrato = df_filtrato[df_filtrato["descrizione"].astype(str).str.lower().str.contains(filtro_causale)]
                
                if df_filtrato.empty:
                    st.warning("Nessuna transazione trovata con questi filtri.")
                else:
                    # 4. MOTORE DI CALCOLO SALDI
                    persone = df_filtrato["persona"].unique()
                    saldi_finali = {}
                    
                    for persona in persone:
                        df_persona = df_filtrato[df_filtrato["persona"] == persona]
                        
                        # Se stiamo filtrando per capire il costo di Spotify o un periodo preciso, saltiamo gli azzeramenti
                        if filtro_causale or (len(filtro_date) == 2 and (start_date != min_date or end_date != max_date)):
                            saldo = df_persona["variazione_credito"].sum()
                        else:
                            condizione_azzeramento = df_persona["sotto categoria"].astype(str).str.lower().str.startswith("azzeramento")
                            df_azzeramento = df_persona[condizione_azzeramento]
                            
                            if not df_azzeramento.empty:
                                ultima_rettifica = df_azzeramento.sort_values(by="data_dt", ascending=False).iloc[0]
                                data_rettifica = ultima_rettifica["data_dt"]
                                saldo_base = ultima_rettifica["variazione_credito"] 
                                df_successive = df_persona[(df_persona["data_dt"] > data_rettifica) & (~condizione_azzeramento)]
                                saldo = saldo_base + df_successive["variazione_credito"].sum()
                            else:
                                saldo = df_persona["variazione_credito"].sum()
                            
                        saldi_finali[persona] = saldo

                    # 5. PANORAMICA GLOBALE FILTRATA
                    totale_da_ricevere = sum(s for s in saldi_finali.values() if s < 0)
                    totale_da_dare = sum(s for s in saldi_finali.values() if s > 0)
                    
                    bilancio_netto = totale_da_ricevere + totale_da_dare
                    
                    col_tot1, col_tot2, col_tot3 = st.columns(3)
                    col_tot1.metric("🟢 Totale da Ricevere", f"{abs(totale_da_ricevere):,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
                    col_tot2.metric("🔴 Totale da Dare", f"{totale_da_dare:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
                    col_tot3.metric("📊 Bilancio Netto", f"{bilancio_netto:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."), delta="Perdita" if bilancio_netto > 0 else "Profitto" if bilancio_netto < 0 else "In Pari", delta_color="inverse")
                    
                    st.divider()

                    # 6. DETTAGLIO FILTRABILE PER PERSONA E CALCOLO GRUPPO
                    st.markdown("### 👤 Dettaglio per Persona")
                    lista_persone = sorted(list(persone))
                    persone_selezionate = st.multiselect(
                        "Filtra per persona (lascia vuoto per vederli tutti):", 
                        options=lista_persone, 
                        default=[]
                    )
                    
                    # --- NOVITÀ: Calcolo totale solo per le persone selezionate ---
                    if persone_selezionate:
                        totale_selezionati = sum(saldi_finali[nome] for nome in persone_selezionate if nome in saldi_finali)
                        st.markdown("#### 🧮 Totale Persone Selezionate")
                        if totale_selezionati > 0.01:
                            st.error(f"🔴 Devi a questo gruppo un totale di: **{abs(totale_selezionati):,.2f} €**")
                        elif totale_selezionati < -0.01:
                            st.success(f"🟢 Questo gruppo ti deve un totale di: **{abs(totale_selezionati):,.2f} €**")
                        else:
                            st.info("⚪ Siete in pari con il gruppo selezionato (0.00 €)")
                        st.markdown("---")
                    
                    # Stampa i saldi singoli
                    for nome, saldo in saldi_finali.items():
                        if persone_selezionate and nome not in persone_selezionate:
                            continue
                            
                        if saldo > 0.01:
                            st.error(f"🔴 Devi a **{nome}**: **{abs(saldo):,.2f} €**")
                        elif saldo < -0.01:
                            st.success(f"🟢 **{nome}** ti deve restituire: **{abs(saldo):,.2f} €**")
                        else:
                            st.info(f"⚪ **{nome}**: Siete in pari (0.00 €)")
                            
                    # 7. STORICO MOVIMENTI
                    st.subheader("Storico dei Movimenti")
                    
                    df_mostra_storico = df_filtrato.copy()
                    if persone_selezionate:
                        df_mostra_storico = df_mostra_storico[df_mostra_storico["persona"].isin(persone_selezionate)]
                        
                    st.dataframe(
                        df_mostra_storico[["data_dt", "persona", "categoria", "sotto categoria", "descrizione", "importo"]]
                        .sort_values(by="data_dt", ascending=False), 
                        use_container_width=True
                    )

# ==========================================
#      PAGINA 4: REGISTRO TRANSAZIONI
# ==========================================
elif pagina_scelta == "📝 Registro Transazioni":
    st.title("Bilancio Personale")
    st.subheader("📝 Registro e Modifiche")
    
    df_storico = carica_storico()
    
    if df_storico.empty:
        st.info("Nessuna transazione trovata.")
    else:
        # 1. STRUMENTO DI MODIFICA / ELIMINAZIONE
        st.markdown("### ✏️ Modifica o Elimina Movimento")
        
        # Ricarichiamo sempre lo storico aggiornato
        df_storico = carica_storico() 
        
        if not df_storico.empty:
            # Creiamo un ID univoco visibile nell'etichetta per evitare confusioni
            df_edit = df_storico.sort_values(by="data_dt", ascending=False).copy()
            df_edit["etichetta"] = (
                df_edit["data"].astype(str) + " | " + 
                df_edit["sotto categoria"].astype(str) + " | " + 
                df_edit["descrizione"].astype(str) + " | " + 
                df_edit["importo"].astype(str) + " €"
            )
            
            # Usiamo un dizionario per mappare etichetta -> riga_gs (così è ultra-veloce)
            mappa_transazioni = dict(zip(df_edit["etichetta"], df_edit["gs_row"]))
            
            lista_opzioni = ["-- Seleziona transazione --"] + df_edit["etichetta"].tolist()
            transazione_selezionata = st.selectbox("Cerca transazione:", lista_opzioni)
            
            if transazione_selezionata != "-- Seleziona transazione --":
                riga_gs = mappa_transazioni[transazione_selezionata]
                riga_dati = df_storico[df_storico["gs_row"] == riga_gs].iloc[0]
            
                if str(riga_dati["flusso"]).lower() == "giroconto":
                    st.warning("💡 Stai modificando un Giroconto: ricordati che i giroconti hanno sempre 2 righe separate. Se modifichi l'importo qui, ricordati di modificare anche l'altra metà per far quadrare i conti!")
                
                # --- PREPARIAMO LE LISTE PER I MENU A TENDINA ---
                lista_flussi = sorted([str(x) for x in df_storico["flusso"].dropna().unique() if str(x).strip()])
                lista_categorie = sorted([str(x) for x in df_storico["categoria"].dropna().unique() if str(x).strip()])
                lista_sottocat = sorted([str(x) for x in df_storico["sotto categoria"].dropna().unique() if str(x).strip()])
                lista_tip = sorted([str(x) for x in df_storico["tipologia"].dropna().unique() if str(x).strip()])

                # Troviamo gli indici attuali (se non li trova, mette 0 di default)
                def trova_indice(lista, valore):
                    try: return lista.index(str(valore))
                    except ValueError: return 0
                
                with st.form("form_modifica"):
                    st.write(f"Modifica dei dati (Riga Database: {riga_gs})")
                    
                    # Prima riga di campi
                    c_data, c_imp, c_conto = st.columns([1, 1, 1.5])
                    with c_data:
                        nuova_data = st.date_input("Data", riga_dati["data_dt"].date())
                    with c_imp:
                        # RIMOSSO l'abs() per permettere numeri negativi negli allineamenti
                        nuovo_importo = st.number_input("Importo (€)", value=float(riga_dati["importo"]), step=0.01)
                    with c_conto:
                        nuova_tipologia = st.selectbox("Conto / Metodo", lista_tip, index=trova_indice(lista_tip, riga_dati["tipologia"]))
                    
                    # Seconda riga di campi (TUTTO MODIFICABILE ORA)
                    c_flusso, c_cat, c_subcat = st.columns(3)
                    with c_flusso:
                        nuovo_flusso = st.selectbox("Flusso", lista_flussi, index=trova_indice(lista_flussi, riga_dati["flusso"]))
                    with c_cat:
                        nuova_cat = st.selectbox("Categoria", lista_categorie, index=trova_indice(lista_categorie, riga_dati["categoria"]))
                    with c_subcat:
                        nuova_subcat = st.selectbox("Sotto Categoria", lista_sottocat, index=trova_indice(lista_sottocat, riga_dati["sotto categoria"]))
                        
                    # Terza riga di campi
                    nuova_desc = st.text_input("Descrizione", str(riga_dati["descrizione"]))
                        
                    # Pulsanti
                    c1, c2 = st.columns(2)
                    with c1:
                        btn_salva = st.form_submit_button("💾 Salva Modifiche")
                    with c2:
                        btn_elimina = st.form_submit_button("🗑️ Elimina Definitivamente")
                        
                # Azione: ELIMINA
                if btn_elimina:
                    try:
                        tab_storico.delete_rows(riga_gs)
                        st.success("✅ Transazione eliminata con successo!")
                        st.cache_data.clear() 
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore durante l'eliminazione: {e}")
                
                # Azione: MODIFICA
                if btn_salva:
                    uscite_calc, entrate_calc, giroconti_calc = 0.0, 0.0, 0.0
                    importo_netto = 0.0
                    
                    # LA NUOVA LOGICA MATEMATICA BASATA SUL FLUSSO SCELTO NEL MENU
                    if nuovo_flusso == "Pagamento":
                        uscite_calc = abs(nuovo_importo) # Forza positivo nella colonna uscite
                        importo_netto = -abs(nuovo_importo) # Forza negativo nel netto
                    elif nuovo_flusso == "Incasso":
                        entrate_calc = abs(nuovo_importo)
                        importo_netto = abs(nuovo_importo)
                    elif str(nuovo_flusso).lower() == "giroconto":
                        if float(riga_dati["importo"]) < 0:
                            giroconti_calc = -abs(nuovo_importo)
                        else:
                            giroconti_calc = abs(nuovo_importo)
                        importo_netto = giroconti_calc
                    elif "allineamento" in str(nuovo_flusso).lower(): # Copre sia "Allineamento saldo" che "patrimonio"
                        # Rispetta il segno che hai inserito (positivo o negativo) e non tocca entrate/uscite
                        importo_netto = nuovo_importo
                    
                    # Pacchetto dati da spedire a Google Sheets (formattato perfettamente come testo)
                    riga_aggiornata = [
                        nuova_data.strftime("%d/%m/%Y"), 
                        str(nuova_data.year), 
                        str(nuova_data.month),
                        f"{uscite_calc:.2f}", 
                        f"{entrate_calc:.2f}", 
                        f"{giroconti_calc:.2f}", 
                        f"{importo_netto:.2f}",
                        nuova_tipologia, 
                        nuova_subcat, 
                        nuova_desc, 
                        nuova_cat, 
                        nuovo_flusso
                    ]
                    
                    try:
                        tab_storico.update(
                            values=[riga_aggiornata], 
                            range_name=f"A{riga_gs}:L{riga_gs}", 
                            value_input_option='RAW'
                        )
                        st.success("✅ Modifica salvata con successo!")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore durante il salvataggio: {e}")

        st.divider()

        # 2. TABELLA VISUALE DEL REGISTRO COMPLETO
        st.markdown("### 📋 Storico Completo")
        
        df_mostra = df_storico.copy()
        
        # Filtri affiancati (3 colonne ora)
        col_f1, col_f2, col_f3 = st.columns(3)
        
        # Filtro Categoria
        tutte_le_cat = ["Tutte"] + sorted([c for c in df_storico["categoria"].dropna().unique().tolist() if str(c).strip()])
        with col_f1:
            cat_selezionata = st.selectbox("Filtra per Categoria:", tutte_le_cat, key="f_cat")
        if cat_selezionata != "Tutte":
            df_mostra = df_mostra[df_mostra["categoria"] == cat_selezionata]
            
        # Filtro Sotto Categoria
        tutte_le_sottocat = ["Tutte"] + sorted([c for c in df_mostra["sotto categoria"].dropna().unique().tolist() if str(c).strip()])
        with col_f2:
            sottocat_selezionata = st.selectbox("Filtra per Sotto Categoria:", tutte_le_sottocat, key="f_sub")
        if sottocat_selezionata != "Tutte":
            df_mostra = df_mostra[df_mostra["sotto categoria"] == sottocat_selezionata]
            
        # Filtro Tipologia (Conto)
        tutte_le_tip = ["Tutte"] + sorted([t for t in df_storico["tipologia"].dropna().unique().tolist() if str(t).strip()])
        with col_f3:
            tip_selezionata = st.selectbox("Filtra per Tipologia:", tutte_le_tip, key="f_tip")
        if tip_selezionata != "Tutte":
            df_mostra = df_mostra[df_mostra["tipologia"] == tip_selezionata]
            
        # Mostriamo la tabella finale
        colonne_vista = [c for c in ["data", "flusso", "categoria", "sotto categoria", "descrizione", "tipologia", "importo"] if c in df_mostra.columns]
        st.dataframe(df_mostra.sort_values(by="data_dt", ascending=False)[colonne_vista], use_container_width=True)

# ==========================================
#       PAGINA 5: IMPOSTAZIONI
# ==========================================
elif pagina_scelta == "⚙️ Impostazioni":
    st.title("Bilancio Personale")
    st.subheader("⚙️ Impostazioni e Nuove Voci")
    
    st.markdown("### 💳 Aggiungi un nuovo Conto o Carta")
    st.write("Inserisci un nuovo metodo di pagamento. Sarà subito disponibile nel menu a tendina.")
    
    with st.form("form_nuovo_conto", clear_on_submit=True):
        nuovo_conto = st.text_input("Nome del nuovo conto (es. PayPal, Satispay):")
        btn_conto = st.form_submit_button("➕ Aggiungi Conto")
        
        if btn_conto:
            if not nuovo_conto.strip():
                st.warning("⚠️ Inserisci un nome valido.")
            elif nuovo_conto.strip() in lista_tipologie:
                st.warning("⚠️ Questo conto esiste già!")
            else:
                try:
                    # Scrive nella prima riga vuota del tab Tipologie
                    tab_tipologie.append_row([nuovo_conto.strip()])
                    st.success(f"✅ Conto '{nuovo_conto}' aggiunto con successo!")
                    st.cache_data.clear() # Svuota la cache per aggiornare le tendine
                    st.rerun() # Ricarica la pagina all'istante
                except Exception as e:
                    st.error(f"Errore durante il salvataggio: {e}")

    st.divider()

    st.markdown("### 📂 Aggiungi una nuova Categoria")
    st.write("Aggiungi una nuova voce per classificare le tue spese, entrate o prestiti.")
    
    with st.form("form_nuova_cat", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            nuova_sottocat = st.text_input("Sotto Categoria (es. cena sushi):")
        with col2:
            nuova_cat = st.text_input("Categoria principale (es. svago):")
            # Mostriamo un piccolo aiuto con le categorie già esistenti
            se_esistenti = sorted(df_elenchi["Categoria"].dropna().unique().tolist()) if not df_elenchi.empty else []
            if se_esistenti:
                st.caption("Attuali: " + ", ".join(se_esistenti[:5]) + "...")
        with col3:
            # --- MODIFICA QUI ---
            # Estrae la lista dei flussi in tempo reale dal database (se esiste) o usa la tua lista_flussi_dinamici
            if not df_elenchi.empty and "Flusso" in df_elenchi.columns:
                flussi_aggiornati = sorted(df_elenchi["Flusso"].dropna().unique().tolist())
            else:
                flussi_aggiornati = lista_flussi_dinamici
                
            nuovo_flusso = st.selectbox("Flusso:", flussi_aggiornati)
            
        btn_cat = st.form_submit_button("➕ Aggiungi al Dizionario")
        
        if btn_cat:
            if not nuova_sottocat.strip() or not nuova_cat.strip():
                st.warning("⚠️ Compila sia la sotto categoria che la categoria principale.")
            else:
                try:
                    # L'ordine delle colonne nel tab Elenchi è: Sotto categoria, Categoria, Flusso
                    nuova_riga = [nuova_sottocat.strip(), nuova_cat.strip().lower(), nuovo_flusso]
                    tab_elenchi.append_row(nuova_riga)
                    st.success(f"✅ Sotto categoria '{nuova_sottocat}' aggiunta con successo!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore durante il salvataggio: {e}")
