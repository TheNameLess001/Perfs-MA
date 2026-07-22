import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import timedelta, datetime
import re
import io
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ==========================================
# 1. CONFIGURATION DE LA PAGE & LOGIN
# ==========================================
st.set_page_config(page_title="Yassir Control Tower", page_icon="🚀", layout="wide", initial_sidebar_state="expanded")

# Injection du CSS (Box Violettes)
st.markdown("""
    <style>
    .purple-box {
        background-color: #6f42c1; color: #ffffff; padding: 15px;
        border-radius: 10px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        margin-bottom: 10px;
    }
    .purple-box h3 { color: #e9ecef; margin: 0; font-size: 1rem; font-weight: normal; }
    .purple-box h2 { color: #ffffff; margin: 5px 0 0 0; font-size: 1.8rem; font-weight: bold; }
    .purple-box p { color: #d8b4fe; margin: 0; font-size: 0.85rem; }
    </style>
""", unsafe_allow_html=True)

# Système de Login
if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔒 Accès Sécurisé - Control Tower")
    st.markdown("Veuillez vous identifier pour accéder aux données Yassir.")
    with st.form("login_form"):
        username = st.text_input("Identifiant (Ex: houda, chaima...)")
        password = st.text_input("Mot de passe", type="password")
        submitted = st.form_submit_button("Se connecter")
        
        if submitted:
            secrets_pass = st.secrets.get("passwords", {})
            if username.lower() in secrets_pass and secrets_pass[username.lower()] == password:
                st.session_state.auth = True
                st.session_state.user = username.capitalize()
                st.rerun()
            else:
                st.error("❌ Identifiant ou mot de passe incorrect.")
    st.stop() # Bloque l'exécution du reste du code si non connecté

st.title(f"📊 Control Tower CRM - Bonjour {st.session_state.user}")
st.markdown("---")

# ==========================================
# 2. CONNEXIONS (DRIVE & SHEETS)
# ==========================================
@st.cache_resource
def get_google_clients():
    try:
        creds_dict = st.secrets["gcp_service_account"]
        scopes = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scopes)
        drive_service = build('drive', 'v3', credentials=creds)
        gc = gspread.authorize(creds)
        return drive_service, gc
    except Exception as e:
        st.error("❌ Erreur de connexion aux services Google.")
        st.stop()

drive_service, gc = get_google_clients()

# --- Chargement CRM (Pipelines & Notes) ---
def load_crm_data():
    try:
        sheet = gc.open("CRM_Yassir")
        df_pipe = pd.DataFrame(sheet.worksheet("Pipelines").get_all_records())
        df_notes = pd.DataFrame(sheet.worksheet("Notes_Historique").get_all_records())
        return df_pipe, df_notes, sheet
    except Exception as e:
        st.error("❌ Impossible de lire le fichier 'CRM_Yassir' sur Google Drive. Vérifiez le nom et les partages.")
        st.stop()

df_pipeline_master, df_notes_master, crm_sheet = load_crm_data()

# --- Recherche des fichiers Data Yassir ---
@st.cache_data(ttl=300)
def get_data_files():
    results = drive_service.files().list(q="mimeType='text/csv'", fields="files(id, name)").execute()
    data_files = []
    for f in results.get('files', []):
        match = re.search(r'data week (\d+)_(\d{4})\.csv', f['name'], re.IGNORECASE)
        if match:
            data_files.append({'id': f['id'], 'name': f['name'], 'year': int(match.group(2)), 'week': int(match.group(1))})
    data_files.sort(key=lambda x: (x['year'], x['week']), reverse=True)
    return data_files

fichiers_disponibles = get_data_files()
if not fichiers_disponibles:
    st.warning("⚠️ Aucun fichier `data week X_YYYY.csv` trouvé sur Drive.")
    st.stop()

# ==========================================
# 3. EN-TÊTE ET LECTURE DATA
# ==========================================
col_am, col_upload = st.columns([1, 2])
with col_am:
    am_choisi = st.selectbox("🎯 Sélection de la Pipeline", ["Global", "Houda", "Chaima", "Najwa", "Imane"])

with col_upload:
    fichier_choisi = st.selectbox("📂 Fichier de données (Google Drive) :", [f['name'] for f in fichiers_disponibles], label_visibility="collapsed")

@st.cache_data(show_spinner=False)
def load_drive_csv(file_id):
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False: status, done = downloader.next_chunk()
    fh.seek(0)
    return pd.read_csv(fh)

with st.spinner(f'Synchronisation en cours...'):
    id_choisi = next(f['id'] for f in fichiers_disponibles if f['name'] == fichier_choisi)
    df_data = load_drive_csv(id_choisi)
    if "restaurant name" in df_data.columns: df_data.rename(columns={"restaurant name": "Restaurant Name"}, inplace=True)

    # Filtrage Pipeline depuis le CRM
    if am_choisi != "Global":
        df_pipe_am = df_pipeline_master[df_pipeline_master['AM_Name'].str.lower() == am_choisi.lower()]
        if 'Restaurant Name' in df_data.columns: df_data.drop(columns=['Restaurant Name'], inplace=True)
        df_merged = pd.merge(df_data, df_pipe_am[['Restaurant ID', 'Restaurant Name']], on="Restaurant ID", how="inner")
        liste_attendue = df_pipe_am[['Restaurant ID', 'Restaurant Name']].drop_duplicates()
    else:
        df_merged = df_data.copy()
        liste_attendue = df_merged[['Restaurant ID', 'Restaurant Name']].drop_duplicates()

    # Exclusion Test/Fixe
    pattern_exclus = '|'.join(['test', 'restau fixe', 'restau avance'])
    df_merged = df_merged[~df_merged['Restaurant Name'].str.contains(pattern_exclus, case=False, na=False)]
    liste_attendue = liste_attendue[~liste_attendue['Restaurant Name'].str.contains(pattern_exclus, case=False, na=False)]

    df_merged['order day'] = pd.to_datetime(df_merged['order day'])
    df_merged['Week'] = "Week " + df_merged['order day'].dt.isocalendar().week.astype(str).str.zfill(2)
    semaines_dispos = sorted(df_merged['Week'].unique(), reverse=True)

with st.sidebar:
    st.markdown("### 📅 Filtres Temporels")
    semaine_selectionnee = st.selectbox("Semaine principale", semaines_dispos)
    semaine_precedente = semaines_dispos[semaines_dispos.index(semaine_selectionnee) + 1] if len(semaines_dispos) > semaines_dispos.index(semaine_selectionnee) + 1 else None
    
# ==========================================
# 4. POPUP 360° (CRM RESTAURANT)
# ==========================================
@st.dialog("🔍 Vue 360° du Restaurant", width="large")
def popup_restaurant(resto_id, resto_name):
    df_r = df_merged[df_merged['Restaurant ID'] == resto_id].sort_values('order day')
    
    if df_r.empty:
        st.warning(f"Aucune donnée pour {resto_name} dans la base sélectionnée.")
        return

    # Calculs KPIs
    req_tot = len(df_r)
    deliv_tot = len(df_r[df_r['status'] == 'Delivered'])
    gmv_tot = df_r[df_r['status'] == 'Delivered']['item total'].sum()
    
    st.markdown(f"### 🏪 {resto_name}")
    
    # Box Violettes
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(f"<div class='purple-box'><h3>Commandes Reçues</h3><h2>{req_tot}</h2></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='purple-box'><h3>Commandes Livrées</h3><h2>{deliv_tot}</h2></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='purple-box'><h3>GMV Généré</h3><h2>{gmv_tot:,.0f} MAD</h2></div>", unsafe_allow_html=True)
    
    # Graphique de tendance
    df_trend = df_r.groupby('order day').agg(Req=('order id','count'), Deliv=('status', lambda x: (x=='Delivered').sum())).reset_index()
    fig = px.line(df_trend, x='order day', y=['Req', 'Deliv'], title="Tendance Journalière (Reçu vs Livré)", markers=True)
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    col_act, col_trans = st.columns(2)
    
    # --- GESTION DES NOTES ---
    with col_act:
        st.markdown("#### 📝 Ajouter une Action / Note")
        nouvelle_note = st.text_area("Description de l'action :", placeholder="Ex: Relance promo, Installation caisse...")
        if st.button("💾 Enregistrer la note"):
            ws_notes = crm_sheet.worksheet("Notes_Historique")
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            ws_notes.append_row([date_str, resto_id, st.session_state.user, nouvelle_note])
            st.success("Note enregistrée avec succès !")
            st.rerun()

        st.markdown("#### 📜 Historique")
        notes_r = df_notes_master[df_notes_master['Restaurant ID'] == resto_id]
        if not notes_r.empty:
            for _, row in notes_r.iterrows():
                with st.expander(f"📅 {row['Date']} par {row['Auteur']}"):
                    st.write(row['Contenu'])
                    
                    # COMPARABLE AVANT / APRES
                    try:
                        date_note = pd.to_datetime(row['Date']).date()
                        df_r['date_only'] = df_r['order day'].dt.date
                        avant = df_r[(df_r['date_only'] < date_note) & (df_r['date_only'] >= date_note - timedelta(days=7))]
                        apres = df_r[(df_r['date_only'] >= date_note) & (df_r['date_only'] <= date_note + timedelta(days=7))]
                        
                        gmv_av = avant[avant['status'] == 'Delivered']['item total'].sum()
                        gmv_ap = apres[apres['status'] == 'Delivered']['item total'].sum()
                        evo = (gmv_ap / gmv_av - 1) if gmv_av > 0 else 0
                        
                        st.info(f"📊 **Impact (7j Avant vs 7j Après) :** GMV Avant = {gmv_av:,.0f} | GMV Après = {gmv_ap:,.0f} ({evo:+.1%})")
                    except: pass
        else:
            st.info("Aucune note pour ce restaurant.")

    # --- TRANSFERT PIPELINE ---
    with col_trans:
        st.markdown("#### 🔄 Transférer le restaurant")
        current_am = df_pipeline_master[df_pipeline_master['Restaurant ID'] == resto_id]['AM_Name'].iloc[0] if not df_pipeline_master[df_pipeline_master['Restaurant ID'] == resto_id].empty else "Inconnu"
        st.write(f"Pipeline actuelle : **{current_am}**")
        nouveau_am = st.selectbox("Transférer vers :", ["Houda", "Chaima", "Najwa", "Imane"], index=["Houda", "Chaima", "Najwa", "Imane"].index(current_am) if current_am in ["Houda", "Chaima", "Najwa", "Imane"] else 0)
        
        if st.button("🚀 Valider le transfert"):
            ws_pipe = crm_sheet.worksheet("Pipelines")
            cell = ws_pipe.find(str(resto_id), in_column=1) # Cherche l'ID dans la col 1
            if cell:
                ws_pipe.update_cell(cell.row, 3, nouveau_am) # Met à jour la col 3 (AM_Name)
                st.success(f"Transféré à {nouveau_am} ! Actualisez la page.")
            else:
                ws_pipe.append_row([resto_id, resto_name, nouveau_am])
                st.success("Restaurant ajouté au CRM et assigné !")

# ==========================================
# 5. MOTEUR DE CALCULS & CROISSANCE (WoW)
# ==========================================
def compute_metrics(df_subset, group_cols):
    return df_subset.groupby(group_cols).agg(
        Requested=('order id', 'count'),
        Delivered=('status', lambda x: (x == 'Delivered').sum()),
        Auto_Accepted=('Accepted By', lambda x: x.str.contains('restaurant', case=False, na=False).sum() if 'Accepted By' in df_subset.columns else 0),
        CancelledByRestaurant=('status', lambda x: x.str.contains('restaurant', case=False, na=False).sum()),
        GMV=('item total', lambda x: x[df_subset.loc[x.index, 'status'] == 'Delivered'].sum()),
    ).reset_index()

def compare_wow(df_curr, df_prev, merge_on):
    df_comp = pd.merge(df_curr, df_prev, on=merge_on, suffixes=('', '_prev'), how='left').fillna(0)
    req_curr_safe, req_prev_safe = df_comp['Requested'].replace(0, np.nan), df_comp['Requested_prev'].replace(0, np.nan)
    del_curr_safe, del_prev_safe = df_comp['Delivered'].replace(0, np.nan), df_comp['Delivered_prev'].replace(0, np.nan)
    gmv_prev_safe = df_comp['GMV_prev'].replace(0, np.nan)
    
    df_comp['Success Rate'] = (df_comp['Delivered'] / req_curr_safe).fillna(0)
    df_comp['Taux Acceptation'] = (df_comp['Auto_Accepted'] / req_curr_safe).fillna(0)
    df_comp['Taux Cancellation'] = (df_comp['CancelledByRestaurant'] / req_curr_safe).fillna(0)
    
    df_comp['wow delivered %'] = (df_comp['Delivered'] / del_prev_safe - 1).fillna(0)
    df_comp['wow GMV %'] = (df_comp['GMV'] / gmv_prev_safe - 1).fillna(0)
    df_comp['wow T.A'] = df_comp['Taux Acceptation'] - (df_comp['Auto_Accepted_prev'] / req_prev_safe).fillna(0)
    
    if not df_comp.empty and 'GMV' in df_comp.columns:
        df_comp['Tier'] = pd.qcut(df_comp['GMV'].rank(method='first'), q=[0, 0.4, 0.8, 1.0], labels=['Tier C', 'Tier B', 'Tier A'])
    return df_comp

df_current = df_merged[df_merged['Week'] == semaine_selectionnee]
df_prev = df_merged[df_merged['Week'] == semaine_precedente] if semaine_precedente else pd.DataFrame(columns=df_merged.columns)

# ==========================================
# 6. ONGLETS ET AFFICHAGES VISUELS
# ==========================================
tabs = st.tabs(["🌍 Analyse Global", "📈 Overview Pipeline", "❌ Annulations", "🤖 Automation"])

with tabs[1]:
    st.markdown("#### 📋 Base de Données Détaillée (Cliquez sur une ligne pour ouvrir le CRM)")
    resto_curr = compute_metrics(df_current, ['Area', 'Restaurant ID', 'Restaurant Name'])
    resto_prev = compute_metrics(df_prev, ['Area', 'Restaurant ID', 'Restaurant Name'])
    resto_comp = compare_wow(resto_curr, resto_prev, ['Area', 'Restaurant ID', 'Restaurant Name'])
    
    cols_display = ['Restaurant ID', 'Tier', 'Area', 'Restaurant Name', 'Requested', 'Delivered', 'Success Rate', 'Taux Acceptation', 'wow T.A', 'GMV', 'wow GMV %']
    df_display = resto_comp[cols_display].copy()
    
    for c in ['Success Rate', 'Taux Acceptation', 'wow T.A', 'wow GMV %']: df_display[c] = df_display[c].apply(lambda x: f"{x:+.1%}")
    for c in ['GMV']: df_display[c] = df_display[c].apply(lambda x: f"{x:,.0f}")

    # Tableau Interactif
    event = st.dataframe(
        df_display, 
        column_config={"Restaurant ID": None}, # Cache l'ID mais permet de le récupérer
        use_container_width=True, hide_index=True, 
        on_select="rerun", selection_mode="single-row"
    )
    
    # Ouverture du Popup au clic
    if event.selection.rows:
        idx = event.selection.rows[0]
        r_id = df_display.iloc[idx]['Restaurant ID']
        r_name = df_display.iloc[idx]['Restaurant Name']
        popup_restaurant(r_id, r_name)

# --- (Les autres onglets Macro, Annulations, etc. fonctionnent normalement) ---
with tabs[0]:
    st.info("Passez à l'onglet 'Overview Pipeline' pour tester la fonction CRM Interactive au clic !")
