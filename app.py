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
st.set_page_config(page_title="Yassir Control Tower CRM", page_icon="🚀", layout="wide", initial_sidebar_state="expanded")

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

if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔒 Accès Sécurisé - Control Tower")
    st.markdown("Veuillez vous identifier pour accéder aux données Yassir.")
    with st.form("login_form"):
        username = st.text_input("Identifiant")
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
    st.stop()

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
        st.error(f"❌ Erreur de connexion aux services Google : {e}")
        st.stop()

drive_service, gc = get_google_clients()

def load_crm_data():
    try:
        sheet = gc.open("CRM_Yassir")
        ws_pipe = sheet.worksheet("Pipelines")
        ws_notes = sheet.worksheet("Notes_Historique")
        
        pipe_records = ws_pipe.get_all_records()
        if not pipe_records: df_pipe = pd.DataFrame(columns=['Restaurant ID', 'Restaurant Name', 'AM_Name'])
        else: df_pipe = pd.DataFrame(pipe_records)
            
        notes_records = ws_notes.get_all_records()
        if not notes_records: df_notes = pd.DataFrame(columns=['Date', 'Restaurant ID', 'Auteur', 'Contenu'])
        else: df_notes = pd.DataFrame(notes_records)
            
        return df_pipe, df_notes, sheet
    except Exception as e:
        st.error(f"❌ Erreur lecture CRM_Yassir : {e}. Vérifiez que les onglets existent et ont bien leurs en-têtes (1ère ligne).")
        st.stop()

df_pipeline_master, df_notes_master, crm_sheet = load_crm_data()

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
# 3. EN-TÊTE ET LECTURE DATA PRINCIPALE
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

try:
    with st.spinner(f'Synchronisation en cours...'):
        id_choisi = next(f['id'] for f in fichiers_disponibles if f['name'] == fichier_choisi)
        df_data = load_drive_csv(id_choisi)
        if "restaurant name" in df_data.columns: df_data.rename(columns={"restaurant name": "Restaurant Name"}, inplace=True)

        if am_choisi != "Global":
            df_pipe_am = df_pipeline_master[df_pipeline_master['AM_Name'].str.lower() == am_choisi.lower()]
            if 'Restaurant Name' in df_data.columns and 'Restaurant Name' in df_pipeline.columns: df_data.drop(columns=['Restaurant Name'], inplace=True)
            df_merged = pd.merge(df_data, df_pipe_am[['Restaurant ID', 'Restaurant Name']], on="Restaurant ID", how="inner")
            liste_attendue = df_pipe_am[['Restaurant ID', 'Restaurant Name']].drop_duplicates()
        else:
            df_merged = df_data.copy()
            df_merged['Segment'] = 'Global'
            liste_attendue = df_merged[['Restaurant ID', 'Restaurant Name']].drop_duplicates()

        pattern_exclus = '|'.join(['test', 'restau fixe', 'restau avance'])
        df_merged = df_merged[~df_merged['Restaurant Name'].str.contains(pattern_exclus, case=False, na=False)]
        liste_attendue = liste_attendue[~liste_attendue['Restaurant Name'].str.contains(pattern_exclus, case=False, na=False)]

        try: df_caisse = pd.read_csv("CaisseMA.csv", sep=None, engine='python')
        except: df_caisse = pd.DataFrame(columns=['Restaurant ID', 'Restaurant Name'])
        
        try: df_new = pd.read_csv("NewRestaurants.csv", sep=None, engine='python')
        except: df_new = pd.DataFrame(columns=['Restaurant ID', 'Restaurant Name'])

        df_merged['order day'] = pd.to_datetime(df_merged['order day'])
        df_merged['Week'] = "Week " + df_merged['order day'].dt.isocalendar().week.astype(str).str.zfill(2)
        semaines_dispos = sorted(df_merged['Week'].unique(), reverse=True)

except Exception as e:
    st.error(f"❌ Erreur critique lors de la lecture du fichier : {e}")
    st.stop()

with st.sidebar:
    st.markdown("### 📅 Filtres Temporels")
    semaine_selectionnee = st.selectbox("Semaine principale", semaines_dispos)
    try: semaine_precedente = semaines_dispos[semaines_dispos.index(semaine_selectionnee) + 1]
    except: semaine_precedente = None
    st.markdown("---")
    st.info(f"**Commandes chargées :** {len(df_merged):,}")

# ==========================================
# 4. MOTEUR DE CALCULS & CROISSANCE (WoW) - AVEC PROTECTION ZÉRO
# ==========================================
def compute_metrics(df_subset, group_cols):
    return df_subset.groupby(group_cols).agg(
        Requested=('order id', 'count'),
        Delivered=('status', lambda x: (x == 'Delivered').sum()),
        Auto_Accepted=('Accepted By', lambda x: x.str.contains('restaurant', case=False, na=False).sum() if 'Accepted By' in df_subset.columns else 0),
        CancelledByRestaurant=('status', lambda x: x.str.contains('restaurant', case=False, na=False).sum()),
        GMV=('item total', lambda x: x[df_subset.loc[x.index, 'status'] == 'Delivered'].sum()),
        CA=('admin earnings', lambda x: x[df_subset.loc[x.index, 'status'] == 'Delivered'].sum()),
        Commission=('restaurant commission', lambda x: x[df_subset.loc[x.index, 'status'] == 'Delivered'].sum()),
        Promo_Restaurant=('coupon restaurant', 'sum'),
        Promo_Admin=('coupon admin', 'sum'),
        LR_LG_Costs=('driver payout', 'sum')
    ).reset_index()

def compare_wow(df_curr, df_prev, merge_on):
    df_comp = pd.merge(df_curr, df_prev, on=merge_on, suffixes=('', '_prev'), how='left').fillna(0)
    
    req_curr_safe, req_prev_safe = df_comp['Requested'].replace(0, np.nan), df_comp['Requested_prev'].replace(0, np.nan)
    del_curr_safe, del_prev_safe = df_comp['Delivered'].replace(0, np.nan), df_comp['Delivered_prev'].replace(0, np.nan)
    gmv_prev_safe = df_comp['GMV_prev'].replace(0, np.nan)
    
    df_comp['Success Rate'] = (df_comp['Delivered'] / req_curr_safe).fillna(0)
    df_comp['Taux Acceptation'] = (df_comp['Auto_Accepted'] / req_curr_safe).fillna(0)
    df_comp['Taux Cancellation'] = (df_comp['CancelledByRestaurant'] / req_curr_safe).fillna(0)
    df_comp['AOV'] = (df_comp['GMV'] / del_curr_safe).fillna(0)
    
    df_comp['wow delivered'] = df_comp['Delivered'] - df_comp['Delivered_prev']
    df_comp['wow delivered %'] = (df_comp['Delivered'] / del_prev_safe - 1).fillna(0)
    df_comp['wow GMV'] = df_comp['GMV'] - df_comp['GMV_prev']
    df_comp['wow GMV %'] = (df_comp['GMV'] / gmv_prev_safe - 1).fillna(0)
    df_comp['wow T.A'] = df_comp['Taux Acceptation'] - (df_comp['Auto_Accepted_prev'] / req_prev_safe).fillna(0)
    df_comp['wow Cancellation'] = df_comp['Taux Cancellation'] - (df_comp['CancelledByRestaurant_prev'] / req_prev_safe).fillna(0)
    df_comp['Wow CA'] = df_comp['CA'] - df_comp['CA_prev']
    
    if not df_comp.empty and 'GMV' in df_comp.columns:
        df_comp['Tier'] = pd.qcut(df_comp['GMV'].rank(method='first'), q=[0, 0.4, 0.8, 1.0], labels=['Tier C', 'Tier B', 'Tier A'])
    return df_comp

df_current = df_merged[df_merged['Week'] == semaine_selectionnee].copy()
df_prev = df_merged[df_merged['Week'] == semaine_precedente] if semaine_precedente else pd.DataFrame(columns=df_merged.columns)

# ==========================================
# 5. POPUP 360° (CRM RESTAURANT)
# ==========================================
@st.dialog("🔍 Vue 360° du Restaurant", width="large")
def popup_restaurant(resto_id, resto_name):
    df_r = df_merged[df_merged['Restaurant ID'] == resto_id].sort_values('order day')
    
    if df_r.empty:
        st.warning(f"Aucune commande pour {resto_name} dans la base sélectionnée.")
        return

    req_tot = len(df_r)
    deliv_tot = len(df_r[df_r['status'] == 'Delivered'])
    gmv_tot = df_r[df_r['status'] == 'Delivered']['item total'].sum()
    
    st.markdown(f"### 🏪 {resto_name}")
    
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(f"<div class='purple-box'><h3>Commandes Reçues</h3><h2>{req_tot}</h2></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='purple-box'><h3>Commandes Livrées</h3><h2>{deliv_tot}</h2></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='purple-box'><h3>GMV Généré</h3><h2>{gmv_tot:,.0f} MAD</h2></div>", unsafe_allow_html=True)
    
    df_trend = df_r.groupby('order day').agg(Req=('order id','count'), Deliv=('status', lambda x: (x=='Delivered').sum())).reset_index()
    fig = px.line(df_trend, x='order day', y=['Req', 'Deliv'], title="Tendance Journalière", markers=True)
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    col_act, col_trans = st.columns(2)
    
    with col_act:
        st.markdown("#### 📝 Ajouter une Action / Note")
        nouvelle_note = st.text_area("Description :", placeholder="Relance promo...")
        if st.button("💾 Enregistrer la note"):
            ws_notes = crm_sheet.worksheet("Notes_Historique")
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            if df_notes_master.empty: ws_notes.append_row(['Date', 'Restaurant ID', 'Auteur', 'Contenu'])
            ws_notes.append_row([date_str, int(resto_id), st.session_state.user, nouvelle_note])
            st.success("Note enregistrée ! Fermez le popup pour actualiser.")

        st.markdown("#### 📜 Historique")
        notes_r = df_notes_master[df_notes_master['Restaurant ID'] == resto_id]
        if not notes_r.empty:
            for _, row in notes_r.iterrows():
                with st.expander(f"📅 {row['Date']} par {row['Auteur']}"):
                    st.write(row['Contenu'])
                    try:
                        date_note = pd.to_datetime(row['Date']).date()
                        df_r['date_only'] = df_r['order day'].dt.date
                        avant = df_r[(df_r['date_only'] < date_note) & (df_r['date_only'] >= date_note - timedelta(days=7))]
                        apres = df_r[(df_r['date_only'] >= date_note) & (df_r['date_only'] <= date_note + timedelta(days=7))]
                        
                        gmv_av = avant[avant['status'] == 'Delivered']['item total'].sum()
                        gmv_ap = apres[apres['status'] == 'Delivered']['item total'].sum()
                        evo = (gmv_ap / gmv_av - 1) if gmv_av > 0 else 0
                        st.info(f"📊 Impact 7j : GMV Avant = {gmv_av:,.0f} | GMV Après = {gmv_ap:,.0f} ({evo:+.1%})")
                    except: pass
        else:
            st.info("Aucune note.")

    with col_trans:
        st.markdown("#### 🔄 Transférer le restaurant")
        current_am = df_pipeline_master[df_pipeline_master['Restaurant ID'] == resto_id]['AM_Name'].iloc[0] if not df_pipeline_master[df_pipeline_master['Restaurant ID'] == resto_id].empty else "Inconnu"
        st.write(f"Pipeline actuelle : **{current_am}**")
        nouveau_am = st.selectbox("Transférer vers :", ["Houda", "Chaima", "Najwa", "Imane"], index=["Houda", "Chaima", "Najwa", "Imane"].index(current_am) if current_am in ["Houda", "Chaima", "Najwa", "Imane"] else 0)
        
        if st.button("🚀 Valider le transfert"):
            ws_pipe = crm_sheet.worksheet("Pipelines")
            try:
                cell = ws_pipe.find(str(resto_id), in_column=1)
                ws_pipe.update_cell(cell.row, 3, nouveau_am)
            except:
                ws_pipe.append_row([int(resto_id), resto_name, nouveau_am])
            st.success(f"Transféré à {nouveau_am} ! Fermez le popup.")


# ==========================================
# 6. CORRECTION DE LA FONCTION MERGE_EXT
# ==========================================
def merge_external_list(df_external, expected_list, comp_df):
    """Permet d'afficher TOUS les restaurants d'une liste sans erreur de Catégorie (Tier)"""
    res = pd.merge(pd.merge(df_external[['Restaurant ID']], expected_list[['Restaurant ID', 'Restaurant Name']], on='Restaurant ID', how='inner'), comp_df.drop(columns=['Restaurant Name'], errors='ignore'), on='Restaurant ID', how='left')
    
    # Remplacement par 0 uniquement pour les colonnes numériques
    metrics_num = ['Requested', 'Delivered', 'GMV', 'wow GMV', 'wow GMV %', 'Success Rate', 'Taux Acceptation', 'wow delivered %']
    for m in metrics_num:
        if m in res.columns:
            res[m] = res[m].fillna(0)
            
    # Traitement sécurisé de la colonne Catégorique "Tier"
    if 'Tier' in res.columns:
        res['Tier'] = res['Tier'].astype(str).replace('nan', 'Non classé')
        
    if 'Area' in res.columns: 
        res['Area'] = res['Area'].fillna('Aucune Cmd')
        
    return res


# ==========================================
# 7. ONGLETS ET AFFICHAGES VISUELS (LES 9 ONGLETS)
# ==========================================
tabs = st.tabs([
    "🌍 1. Macro", "📈 2. Overview", "❌ 3. Annulations", 
    "🤖 4. Auto", "💻 5. Caisse.ma", "✨ 6. New", 
    "👻 7. Inactifs", "🏆 8. Héros", "🍕 9. Catégories"
])

# -- ONGLET 1 --
with tabs[0]:
    st.markdown("#### 🌍 Analyse Macro")
    df_macro = df_merged.groupby('Week').agg(
        Reçu=('order id', 'count'), Livré=('status', lambda x: (x == 'Delivered').sum()),
        GMV=('item total', lambda x: x[df_merged.loc[x.index, 'status'] == 'Delivered'].sum())
    ).reset_index().sort_values(by='Week', ascending=False)
    st.dataframe(df_macro, use_container_width=True, hide_index=True)

# -- ONGLET 2 (AVEC CLICK POPUP) --
with tabs[1]:
    st.markdown("#### 📋 Base Détaillée (🖱️ Cliquez sur une ligne pour ouvrir le CRM)")
    resto_curr, resto_prev = compute_metrics(df_current, ['Area', 'Restaurant ID', 'Restaurant Name']), compute_metrics(df_prev, ['Area', 'Restaurant ID', 'Restaurant Name'])
    resto_comp = compare_wow(resto_curr, resto_prev, ['Area', 'Restaurant ID', 'Restaurant Name'])
    
    cols = ['Restaurant ID', 'Tier', 'Restaurant Name', 'Requested', 'Delivered', 'Success Rate', 'Taux Acceptation', 'wow T.A', 'GMV', 'wow GMV %']
    df_disp = resto_comp[cols].copy()
    for c in ['Success Rate', 'Taux Acceptation', 'wow T.A', 'wow GMV %']: df_disp[c] = df_disp[c].apply(lambda x: f"{x:+.1%}")
    for c in ['GMV']: df_disp[c] = df_disp[c].apply(lambda x: f"{x:,.0f}")

    event = st.dataframe(df_disp, column_config={"Restaurant ID": None}, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
    if event.selection.rows:
        idx = event.selection.rows[0]
        popup_restaurant(df_disp.iloc[idx]['Restaurant ID'], df_disp.iloc[idx]['Restaurant Name'])

# -- ONGLET 3 --
with tabs[2]:
    st.markdown("#### ❌ Annulations")
    df_canc = df_current[df_current['status'].str.contains('Cancelled', case=False, na=False)]
    if not df_canc.empty: st.plotly_chart(px.pie(df_canc['cancellation reason '].value_counts().reset_index(), names='cancellation reason ', values='count', hole=0.4))

# -- ONGLET 4 --
with tabs[3]:
    st.markdown("#### 🤖 Automatisation (Accepted By)")
    if 'Accepted By' in df_current.columns:
        df_current['Is_Auto'] = df_current['Accepted By'].str.contains('restaurant', case=False, na=False)
        auto_recap = df_current.groupby('Is_Auto').agg(Req=('order id', 'count'), Del=('status', lambda x: (x == 'Delivered').sum())).reset_index()
        auto_recap['Type'] = auto_recap['Is_Auto'].map({True: '🤖 Automatisé', False: '👨‍💻 Manuel'})
        st.dataframe(auto_recap[['Type', 'Req', 'Del']], hide_index=True)

# -- ONGLET 5 --
with tabs[4]:
    st.markdown("#### 💻 Caisse.ma")
    if not df_caisse.empty:
        df_caisse_comp = merge_external_list(df_caisse, liste_attendue, resto_comp)
        if not df_caisse_comp.empty: st.dataframe(df_caisse_comp[['Restaurant Name', 'Requested', 'GMV']], hide_index=True)

# -- ONGLET 6 --
with tabs[5]:
    st.markdown("#### ✨ New Restaurants")
    if not df_new.empty:
        df_new_comp = merge_external_list(df_new, liste_attendue, resto_comp)
        if not df_new_comp.empty: st.dataframe(df_new_comp[['Restaurant Name', 'Requested', 'GMV']], hide_index=True)

# -- ONGLET 7 --
with tabs[6]:
    st.markdown("#### 👻 Inactifs")
    max_d = df_merged['order day'].max()
    restos_actifs = df_merged[df_merged['order day'] >= max_d - timedelta(days=7)]['Restaurant ID'].unique()
    restos_inactifs = liste_attendue[~liste_attendue['Restaurant ID'].isin(restos_actifs)]
    st.error(f"⚠️ {len(restos_inactifs)} restaurants inactifs depuis 7j")
    st.dataframe(restos_inactifs[['Restaurant Name']], hide_index=True)

# -- ONGLET 8 --
with tabs[7]:
    st.markdown("#### 🏆 Produits Héros")
    if 'Food Item' in df_current.columns:
        df_items = df_current.assign(Item=df_current['Food Item'].astype(str).str.replace(r'\[|\]|\{\d+\}', '', regex=True).str.split(',')).explode('Item')
        df_items['Item'] = df_items['Item'].str.strip()
        st.dataframe(df_items[(df_items['Item'] != 'nan') & (df_items['Item'] != '')]['Item'].value_counts().head(15).reset_index())

# -- ONGLET 9 --
with tabs[8]:
    st.markdown("#### 🍕 Catégories Food")
    if 'Food Category' in df_current.columns:
        df_cat = compute_metrics(df_current[df_current['Food Category'].astype(str) != 'nan'], ['Food Category'])
        st.plotly_chart(px.bar(df_cat.sort_values('GMV', ascending=False).head(10), x='Food Category', y='GMV'))
