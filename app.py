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
        df_pipe = pd.DataFrame(pipe_records) if pipe_records else pd.DataFrame(columns=['Restaurant ID', 'Restaurant Name', 'AM_Name'])
            
        notes_records = ws_notes.get_all_records()
        df_notes = pd.DataFrame(notes_records) if notes_records else pd.DataFrame(columns=['Date', 'Restaurant ID', 'Auteur', 'Contenu'])
            
        return df_pipe, df_notes, sheet
    except Exception as e:
        st.error(f"❌ Erreur lecture CRM_Yassir : {e}. Vérifiez que les onglets existent.")
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

        # Logique de fusion Global vs Pipeline
        if am_choisi != "Global":
            df_pipe_am = df_pipeline_master[df_pipeline_master['AM_Name'].str.lower() == am_choisi.lower()]
            if 'Restaurant Name' in df_data.columns and 'Restaurant Name' in df_pipe_am.columns: df_data.drop(columns=['Restaurant Name'], inplace=True)
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
    st.success(f"**Périmètre :** {am_choisi}")
    st.info(f"**Commandes chargées :** {len(df_merged):,}")

# ==========================================
# 4. MOTEUR DE CALCULS & CROISSANCE (WoW) 
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
    
    req_curr_safe = df_comp['Requested'].replace(0, np.nan)
    req_prev_safe = df_comp['Requested_prev'].replace(0, np.nan)
    del_curr_safe = df_comp['Delivered'].replace(0, np.nan)
    del_prev_safe = df_comp['Delivered_prev'].replace(0, np.nan)
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
    df_comp['Wow AOV'] = df_comp['AOV'] - (df_comp['GMV_prev'] / del_prev_safe).fillna(0)
    df_comp['Wow Promo Order'] = (df_comp['Promo_Restaurant'] + df_comp['Promo_Admin']) - (df_comp['Promo_Restaurant_prev'] + df_comp['Promo_Admin_prev'])
    df_comp['Wow LR_LG_Costs'] = df_comp['LR_LG_Costs'] - df_comp['LR_LG_Costs_prev']
    
    if not df_comp.empty and 'GMV' in df_comp.columns:
        # CORRECTION : Protection s'il y a moins de 3 lignes (ex: seulement 1 ou 2 villes)
        if len(df_comp) >= 3:
            df_comp['Tier'] = pd.qcut(df_comp['GMV'].rank(method='first'), q=[0, 0.4, 0.8, 1.0], labels=['Tier C', 'Tier B', 'Tier A'])
        else:
            df_comp['Tier'] = 'Non classé'
    else:
        df_comp['Tier'] = "N/A"
        
    return df_comp

def merge_external_list(df_external, expected_list, comp_df):
    res = pd.merge(pd.merge(df_external[['Restaurant ID']], expected_list[['Restaurant ID', 'Restaurant Name']], on='Restaurant ID', how='inner'), comp_df.drop(columns=['Restaurant Name'], errors='ignore'), on='Restaurant ID', how='left')
    metrics_num = ['Requested', 'Delivered', 'GMV', 'wow GMV', 'wow GMV %', 'Success Rate', 'Taux Acceptation', 'wow delivered %']
    for m in metrics_num:
        if m in res.columns: res[m] = res[m].fillna(0)
    if 'Tier' in res.columns: res['Tier'] = res['Tier'].astype(str).replace('nan', 'Non classé')
    if 'Area' in res.columns: res['Area'] = res['Area'].fillna('Aucune Cmd')
    return res

df_current = df_merged[df_merged['Week'] == semaine_selectionnee].copy()
df_prev = df_merged[df_merged['Week'] == semaine_precedente] if semaine_precedente else pd.DataFrame(columns=df_merged.columns)

# ==========================================
# 5. POPUP 360° (CRM RESTAURANT)
# ==========================================
@st.dialog("🔍 Vue 360° du Restaurant", width="large")
def popup_restaurant(resto_id, resto_name):
    df_r = df_merged[df_merged['Restaurant ID'].astype(str) == str(resto_id)].sort_values('order day')
    
    if df_r.empty:
        st.warning(f"Aucune commande trouvée pour {resto_name} dans la base de données sélectionnée.")
        return

    req_tot = len(df_r)
    deliv_tot = len(df_r[df_r['status'] == 'Delivered'])
    gmv_tot = df_r[df_r['status'] == 'Delivered']['item total'].sum()
    
    # Calculs WoW et MoM
    max_d = df_r['order day'].max()
    
    c_7 = df_r[df_r['order day'] >= max_d - timedelta(days=7)]
    p_7 = df_r[(df_r['order day'] >= max_d - timedelta(days=14)) & (df_r['order day'] < max_d - timedelta(days=7))]
    gmv_c7 = c_7[c_7['status']=='Delivered']['item total'].sum()
    gmv_p7 = p_7[p_7['status']=='Delivered']['item total'].sum()
    wow = (gmv_c7 / gmv_p7 - 1) if gmv_p7 > 0 else 0
    
    c_30 = df_r[df_r['order day'] >= max_d - timedelta(days=30)]
    p_30 = df_r[(df_r['order day'] >= max_d - timedelta(days=60)) & (df_r['order day'] < max_d - timedelta(days=30))]
    gmv_c30 = c_30[c_30['status']=='Delivered']['item total'].sum()
    gmv_p30 = p_30[p_30['status']=='Delivered']['item total'].sum()
    mom = (gmv_c30 / gmv_p30 - 1) if gmv_p30 > 0 else 0

    st.markdown(f"### 🏪 {resto_name}")
    
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(f"<div class='purple-box'><h3>Commandes Reçues</h3><h2>{req_tot}</h2></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='purple-box'><h3>Commandes Livrées</h3><h2>{deliv_tot}</h2></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='purple-box'><h3>GMV Généré</h3><h2>{gmv_tot:,.0f} MAD</h2><p>WoW: {wow:+.1%} | MoM: {mom:+.1%}</p></div>", unsafe_allow_html=True)
    
    df_trend = df_r.groupby('order day').agg(Req=('order id','count'), Deliv=('status', lambda x: (x=='Delivered').sum())).reset_index()
    fig = px.line(df_trend, x='order day', y=['Req', 'Deliv'], title="Tendance Journalière (Reçu vs Livré)", markers=True)
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    col_act, col_trans = st.columns(2)
    
    with col_act:
        st.markdown("#### 📝 Ajouter une Action / Note")
        nouvelle_note = st.text_area("Description :", placeholder="Ex: Relance promo, Installation caisse...", key=f"note_{resto_id}")
        if st.button("💾 Enregistrer la note", key=f"btn_{resto_id}"):
            ws_notes = crm_sheet.worksheet("Notes_Historique")
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            if df_notes_master.empty: ws_notes.append_row(['Date', 'Restaurant ID', 'Auteur', 'Contenu'])
            ws_notes.append_row([date_str, str(resto_id), st.session_state.user, nouvelle_note])
            st.success("Note enregistrée ! Fermez le popup pour actualiser.")

        st.markdown("#### 📜 Historique & Impact Avant/Après")
        notes_r = df_notes_master[df_notes_master['Restaurant ID'].astype(str) == str(resto_id)]
        if not notes_r.empty:
            for idx_note, row in notes_r.iterrows():
                with st.expander(f"📅 {row['Date']} par {row['Auteur']}"):
                    st.write(row['Contenu'])
                    
                    jours = st.radio("Période d'analyse :", [7, 15, 30], format_func=lambda x: f"{x} Jours", horizontal=True, key=f"radio_{idx_note}_{resto_id}")
                    try:
                        date_note = pd.to_datetime(row['Date']).date()
                        df_r['date_only'] = df_r['order day'].dt.date
                        avant = df_r[(df_r['date_only'] < date_note) & (df_r['date_only'] >= date_note - timedelta(days=jours))]
                        apres = df_r[(df_r['date_only'] >= date_note) & (df_r['date_only'] <= date_note + timedelta(days=jours))]
                        
                        gmv_av = avant[avant['status'] == 'Delivered']['item total'].sum()
                        gmv_ap = apres[apres['status'] == 'Delivered']['item total'].sum()
                        evo = (gmv_ap / gmv_av - 1) if gmv_av > 0 else 0
                        st.info(f"📊 Impact ({jours}j Avant vs Après) : GMV Avant = {gmv_av:,.0f} | GMV Après = {gmv_ap:,.0f} ({evo:+.1%})")
                    except: pass
        else:
            st.info("Aucune note pour ce restaurant.")

    with col_trans:
        st.markdown("#### 🔄 Transférer le restaurant")
        pipe_am = df_pipeline_master[df_pipeline_master['Restaurant ID'].astype(str) == str(resto_id)]
        current_am = pipe_am['AM_Name'].iloc[0] if not pipe_am.empty else "Global / Inconnu"
        st.write(f"Pipeline actuelle : **{current_am}**")
        nouveau_am = st.selectbox("Transférer vers :", ["Houda", "Chaima", "Najwa", "Imane"], key=f"trans_{resto_id}")
        
        if st.button("🚀 Valider le transfert", key=f"btn_trans_{resto_id}"):
            ws_pipe = crm_sheet.worksheet("Pipelines")
            try:
                cell = ws_pipe.find(str(resto_id), in_column=1)
                ws_pipe.update_cell(cell.row, 3, nouveau_am)
            except:
                ws_pipe.append_row([str(resto_id), resto_name, nouveau_am])
            st.success(f"Transféré à {nouveau_am} ! Fermez le popup.")

# ==========================================
# 6. ONGLETS ET AFFICHAGES VISUELS (BASE 1 COMPLÈTE)
# ==========================================
tabs = st.tabs([
    "🌍 1. Analyse Global", "📈 2. Overview Pipeline", "❌ 3. Annulations",
    "🤖 4. Automation", "💻 5. Caisse.ma", "✨ 6. New Restaurants",
    "👻 7. Inactifs", "🏆 8. Produits Héros", "🍕 9. Catégories Food"
])

# ----------------------------------------
# ONGLET 1 : ANALYSE GLOBAL (MACRO)
# ----------------------------------------
with tabs[0]:
    st.markdown("#### 🌍 Analyse Macro des Performances")
    vue_temporelle = st.radio("Sélectionnez la vue globale :", ["📅 Jour", "📊 Week over Week (WoW)"], horizontal=True)
    
    df_macro_base = df_merged.copy()
    if vue_temporelle == "📅 Jour":
        df_macro_base['Période'] = df_macro_base['order day'].dt.strftime('%Y-%m-%d')
    else:
        df_macro_base['Période'] = df_macro_base['Week']

    df_macro = df_macro_base.groupby('Période').agg(
        Reçu=('order id', 'count'),
        Livré=('status', lambda x: (x == 'Delivered').sum()),
        GMV=('item total', lambda x: x[df_macro_base.loc[x.index, 'status'] == 'Delivered'].sum()),
        CA=('admin earnings', lambda x: x[df_macro_base.loc[x.index, 'status'] == 'Delivered'].sum())
    ).reset_index()

    df_macro['AOV'] = (df_macro['GMV'] / df_macro['Livré'].replace(0, np.nan)).fillna(0)
    df_macro = df_macro.sort_values(by='Période', ascending=True)

    df_macro['V. Reçu'] = df_macro['Reçu'].pct_change()
    df_macro['V. Livré'] = df_macro['Livré'].pct_change()
    df_macro['V. GMV'] = df_macro['GMV'].pct_change()
    df_macro['V. CA'] = df_macro['CA'].pct_change()
    df_macro['V. AOV'] = df_macro['AOV'].pct_change()

    df_macro_display = df_macro.sort_values(by='Période', ascending=False).copy()
    for col in ['V. Reçu', 'V. Livré', 'V. GMV', 'V. CA', 'V. AOV']:
        df_macro_display[col] = df_macro_display[col].apply(lambda x: f"{x:+.1%}" if pd.notnull(x) else "-")
    for col in ['GMV', 'CA', 'AOV']:
        df_macro_display[col] = df_macro_display[col].apply(lambda x: f"{x:,.2f}")

    st.dataframe(df_macro_display[['Période', 'Reçu', 'Livré', 'GMV', 'CA', 'AOV', 'V. Reçu', 'V. Livré', 'V. GMV', 'V. CA', 'V. AOV']], use_container_width=True, hide_index=True)
    st.markdown("---")
    
    df_daily = compute_metrics(df_merged, ['order day']).sort_values('order day')
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.plotly_chart(px.line(df_daily, x="order day", y="GMV", title="Tendance GMV", markers=True, template="plotly_white"), use_container_width=True)
    with col_g2:
        st.plotly_chart(px.line(df_daily, x="order day", y="Requested", title="Tendance Commandes Reçues", markers=True, template="plotly_white", color_discrete_sequence=['#f39c12']), use_container_width=True)
        
    st.markdown("---")
    
    if 'city' in df_merged.columns and 'Area' in df_merged.columns:
        city_curr, city_prev = compute_metrics(df_current, ['city']), compute_metrics(df_prev, ['city'])
        city_comp = compare_wow(city_curr, city_prev, ['city'])
        area_curr, area_prev = compute_metrics(df_current, ['city', 'Area']), compute_metrics(df_prev, ['city', 'Area'])
        area_comp = compare_wow(area_curr, area_prev, ['city', 'Area'])
        
        col_city, col_area = st.columns(2)
        with col_city:
            st.markdown("##### 🏙️ Performances par Ville")
            disp_city = city_comp[['city', 'Requested', 'wow delivered %', 'GMV', 'wow GMV %', 'Success Rate', 'wow T.A']].copy()
            st.dataframe(disp_city.style.format({'wow delivered %': '{:+.1%}', 'GMV': '{:,.0f}', 'wow GMV %': '{:+.1%}', 'Success Rate': '{:.1%}', 'wow T.A': '{:+.1%}'}), hide_index=True)
        with col_area:
            st.markdown("##### 🏘️ Performances par Zone (Area)")
            disp_area = area_comp[['Area', 'Requested', 'wow delivered %', 'GMV', 'wow GMV %', 'Success Rate', 'wow T.A']].sort_values('Requested', ascending=False).head(15).copy()
            st.dataframe(disp_area.style.format({'wow delivered %': '{:+.1%}', 'GMV': '{:,.0f}', 'wow GMV %': '{:+.1%}', 'Success Rate': '{:.1%}', 'wow T.A': '{:+.1%}'}), hide_index=True)

# ----------------------------------------
# ONGLET 2 : OVERVIEW PIPELINE & TOPS/FLOPS
# ----------------------------------------
with tabs[1]:
    st.markdown("#### 📋 Base de Données Détaillée (🖱️ Cliquez sur une ligne pour ouvrir le CRM)")
    resto_curr, resto_prev = compute_metrics(df_current, ['Area', 'Restaurant ID', 'Restaurant Name']), compute_metrics(df_prev, ['Area', 'Restaurant ID', 'Restaurant Name'])
    resto_comp = compare_wow(resto_curr, resto_prev, ['Area', 'Restaurant ID', 'Restaurant Name'])
    
    cols_big_table = [
        'Restaurant ID', 'Tier', 'Area', 'Restaurant Name', 'Requested', 'Delivered', 'Success Rate', 
        'Auto_Accepted', 'Taux Acceptation', 'CancelledByRestaurant', 'Taux Cancellation', 
        'GMV', 'AOV', 'Commission', 'Promo_Restaurant', 'Promo_Admin', 'LR_LG_Costs',
        'wow delivered', 'wow delivered %', 'wow T.A', 'wow Cancellation', 
        'wow GMV', 'wow GMV %', 'Wow CA', 'Wow AOV', 'Wow Promo Order', 'Wow LR_LG_Costs'
    ]
    
    df_pipeline_display = resto_comp[cols_big_table].copy()
    for c in ['Success Rate', 'Taux Acceptation', 'Taux Cancellation', 'wow delivered %', 'wow T.A', 'wow Cancellation', 'wow GMV %']:
        df_pipeline_display[c] = df_pipeline_display[c].apply(lambda x: f"{x:+.1%}")
    for c in ['GMV', 'AOV', 'Commission', 'Promo_Restaurant', 'Promo_Admin', 'LR_LG_Costs', 'wow GMV', 'Wow CA', 'Wow AOV', 'Wow Promo Order', 'Wow LR_LG_Costs']:
        df_pipeline_display[c] = df_pipeline_display[c].apply(lambda x: f"{x:,.1f}")

    event = st.dataframe(df_pipeline_display, column_config={"Restaurant ID": None}, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
    if event.selection.rows:
        idx = event.selection.rows[0]
        popup_restaurant(df_pipeline_display.iloc[idx]['Restaurant ID'], df_pipeline_display.iloc[idx]['Restaurant Name'])
    
    anomalies = resto_comp[(resto_comp['Tier'] == 'Tier A') & (resto_comp['wow delivered %'] < -0.15)]
    if not anomalies.empty:
        st.error(f"🚨 **ALERTE BUSINESS :** {len(anomalies)} restaurants du 'Tier A' ont subi une baisse de plus de 15% des commandes WoW !")
        st.dataframe(anomalies[['Restaurant Name', 'Area', 'Requested', 'wow delivered %', 'wow GMV']].style.format({'wow delivered %': '{:+.1%}', 'wow GMV': '{:+,.0f}'}), hide_index=True)

    st.markdown("---")
    st.markdown("#### 📈 Tops & Flops (Croissance Commandes Livrées)")
    col_t, col_f = st.columns(2)
    with col_t:
        st.success("🏆 **Top 10 Accélérations**")
        st.dataframe(resto_comp.sort_values('wow delivered', ascending=False).head(10)[['Restaurant Name', 'Tier', 'wow delivered', 'wow delivered %']].style.format({'wow delivered %': '{:+.1%}'}), hide_index=True)
    with col_f:
        st.error("📉 **Flop 10 Chutes**")
        st.dataframe(resto_comp.sort_values('wow delivered', ascending=True).head(10)[['Restaurant Name', 'Tier', 'wow delivered', 'wow delivered %']].style.format({'wow delivered %': '{:+.1%}'}), hide_index=True)

# ----------------------------------------
# ONGLET 3 : ANNULATIONS
# ----------------------------------------
with tabs[2]:
    st.markdown("#### ❌ Surveillance des Annulations")
    df_canc_curr = df_current[df_current['status'].str.contains('Cancelled', case=False, na=False)]
    
    col_c1, col_c2 = st.columns([1, 2])
    with col_c1:
        st.markdown("**Comparatif Global vs Area**")
        if 'Area' in df_canc_curr.columns:
            canc_area = df_canc_curr.groupby('Area').size().reset_index(name='Annulations')
            req_area = df_current.groupby('Area').size().reset_index(name='Total Req')
            m_area = pd.merge(canc_area, req_area, on='Area')
            m_area['% Cancel'] = m_area['Annulations'] / m_area['Total Req']
            st.dataframe(m_area.sort_values('% Cancel', ascending=False).head(10).style.format({'% Cancel': '{:.1%}'}), hide_index=True)
            
    with col_c2:
        st.markdown("**Motifs d'Annulations**")
        if not df_canc_curr.empty:
            reasons = df_canc_curr['cancellation reason '].value_counts().reset_index()
            reasons.columns = ['Motif', 'Nombre']
            fig_pie = px.pie(reasons, names='Motif', values='Nombre', hole=0.4)
            fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("---")
    st.markdown("#### 🚨 Les Récidivistes (Restaurants annulant le plus)")
    resto_canc = resto_comp[['Restaurant Name', 'Area', 'Requested', 'CancelledByRestaurant', 'Taux Cancellation', 'wow Cancellation']].copy()
    pires = resto_canc[resto_canc['Requested'] > 5].sort_values('Taux Cancellation', ascending=False).head(15)
    st.dataframe(pires.style.format({'Taux Cancellation': '{:.1%}', 'wow Cancellation': '{:+.1%}'}), use_container_width=True, hide_index=True)

# ----------------------------------------
# ONGLET 4 : AUTOMATION
# ----------------------------------------
with tabs[3]:
    st.markdown("#### 🤖 Suivi de l'Automatisation (Accepted By)")
    if 'Accepted By' in df_current.columns:
        df_current['Is_Auto'] = df_current['Accepted By'].str.contains('restaurant', case=False, na=False)
        auto_recap = df_current.groupby('Is_Auto').agg(
            Requested=('order id', 'count'),
            Delivered=('status', lambda x: (x == 'Delivered').sum()),
            GMV=('item total', lambda x: x[df_current.loc[x.index, 'status'] == 'Delivered'].sum())
        ).reset_index()
        auto_recap['Success Rate'] = (auto_recap['Delivered'] / auto_recap['Requested'].replace(0, np.nan)).fillna(0)
        auto_recap['Type'] = auto_recap['Is_Auto'].map({True: '🤖 Automatisé (Via App/Caisse)', False: '👨‍💻 Manuel / Admin'})
        
        st.markdown("**📊 Impact de l'Automatisation sur les performances globales**")
        st.dataframe(auto_recap[['Type', 'Requested', 'Delivered', 'Success Rate', 'GMV']].style.format({'Success Rate': '{:.1%}', 'GMV': '{:,.0f} MAD'}), hide_index=True)
    
    st.markdown("---")
    col_acc, col_reg = st.columns(2)
    cols_to_show = ['Restaurant Name', 'Requested', 'Taux Acceptation', 'wow T.A']
    with col_acc:
        st.success("**🚀 Accélérations (Effort d'automatisation)**")
        df_acc = resto_comp[resto_comp['wow T.A'] > 0].sort_values('wow T.A', ascending=False).head(10)
        st.dataframe(df_acc[cols_to_show].style.format({'Taux Acceptation': '{:.1%}', 'wow T.A': '{:+.1%}'}), hide_index=True, use_container_width=True)
    with col_reg:
        st.error("**⚠️ Régressions (Retour au manuel)**")
        df_reg = resto_comp[resto_comp['wow T.A'] < 0].sort_values('wow T.A', ascending=True).head(10)
        st.dataframe(df_reg[cols_to_show].style.format({'Taux Acceptation': '{:.1%}', 'wow T.A': '{:+.1%}'}), hide_index=True, use_container_width=True)

# ----------------------------------------
# ONGLET 5 : CAISSE.MA
# ----------------------------------------
with tabs[4]:
    st.markdown("#### 💻 Intégration Caisse.ma (🖱️ Cliquable)")
    if df_caisse.empty:
        st.warning("⚠️ Fichier `CaisseMA.csv` introuvable. Uploadez-le à la racine du projet.")
    else:
        df_caisse_comp = merge_external_list(df_caisse, liste_attendue, resto_comp)
        if df_caisse_comp.empty:
            st.info("Aucun restaurant de cette vue n'est équipé de Caisse.ma.")
        else:
            st.success(f"📍 Affichage exhaustif : **{len(df_caisse_comp)} restaurants** Caisse.ma dans ce périmètre.")
            disp_caisse = df_caisse_comp[['Restaurant ID', 'Restaurant Name', 'Area', 'Requested', 'wow delivered %', 'GMV', 'wow GMV %', 'Taux Acceptation', 'Success Rate']].copy()
            for c in ['Success Rate', 'Taux Acceptation', 'wow delivered %', 'wow GMV %']: disp_caisse[c] = disp_caisse[c].apply(lambda x: f"{x:+.1%}")
            disp_caisse['GMV'] = disp_caisse['GMV'].apply(lambda x: f"{x:,.0f}")
            
            event_c = st.dataframe(disp_caisse, column_config={"Restaurant ID": None}, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row")
            if event_c.selection.rows:
                idx = event_c.selection.rows[0]
                popup_restaurant(disp_caisse.iloc[idx]['Restaurant ID'], disp_caisse.iloc[idx]['Restaurant Name'])

# ----------------------------------------
# ONGLET 6 : NEW RESTAURANTS
# ----------------------------------------
with tabs[5]:
    st.markdown("#### ✨ Performances Nouveaux Restaurants (🖱️ Cliquable)")
    if df_new.empty:
        st.warning("⚠️ Fichier `NewRestaurants.csv` introuvable. Uploadez-le à la racine du projet.")
    else:
        df_new_comp = merge_external_list(df_new, liste_attendue, resto_comp)
        if df_new_comp.empty:
            st.info("Aucun nouveau restaurant dans ce périmètre.")
        else:
            st.success(f"📍 Affichage exhaustif : **{len(df_new_comp)} Nouveaux Restaurants** dans ce périmètre.")
            disp_new = df_new_comp[['Restaurant ID', 'Restaurant Name', 'Area', 'Requested', 'Delivered', 'Success Rate', 'Taux Acceptation', 'GMV', 'wow GMV %']].copy()
            for c in ['Success Rate', 'Taux Acceptation', 'wow GMV %']: disp_new[c] = disp_new[c].apply(lambda x: f"{x:+.1%}")
            disp_new['GMV'] = disp_new['GMV'].apply(lambda x: f"{x:,.0f}")

            event_n = st.dataframe(disp_new, column_config={"Restaurant ID": None}, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row")
            if event_n.selection.rows:
                idx = event_n.selection.rows[0]
                popup_restaurant(disp_new.iloc[idx]['Restaurant ID'], disp_new.iloc[idx]['Restaurant Name'])

# ----------------------------------------
# ONGLET 7 : INACTIFS
# ----------------------------------------
with tabs[6]:
    st.markdown("#### 👻 Surveillance des Inactifs (Aucune Commande)")
    jours_inactifs = st.radio("Signaler les restaurants inactifs depuis :", [3, 7, 15, 30], format_func=lambda x: f"{x} Jours", horizontal=True)
    max_date = df_merged['order day'].max()
    threshold_date = max_date - timedelta(days=jours_inactifs)
    
    df_window = df_merged[df_merged['order day'] >= threshold_date]
    restos_actifs = df_window['Restaurant ID'].unique()
    restos_inactifs = liste_attendue[~liste_attendue['Restaurant ID'].isin(restos_actifs)]
    
    if restos_inactifs.empty:
        st.success(f"🎉 Parfait ! Tous les restaurants ont reçu au moins 1 commande ces {jours_inactifs} derniers jours !")
    else:
        st.error(f"⚠️ **{len(restos_inactifs)} restaurants** n'ont reçu aucune commande depuis {jours_inactifs} jours !")
        st.dataframe(restos_inactifs[['Restaurant Name']], hide_index=True, use_container_width=True)

# ----------------------------------------
# ONGLET 8 : PRODUITS HÉROS
# ----------------------------------------
with tabs[7]:
    st.markdown(f"#### 🏆 Produits Héros - Les Meilleures Ventes ({semaine_selectionnee})")
    if 'Food Item' in df_current.columns:
        df_items = df_current.copy()
        df_items['Clean_Item'] = df_items['Food Item'].astype(str).str.replace(r'\[|\]|\{\d+\}', '', regex=True)
        df_items = df_items.assign(Item=df_items['Clean_Item'].str.split(',')).explode('Item')
        df_items['Item'] = df_items['Item'].str.strip()
        df_items = df_items[(df_items['Item'] != 'nan') & (df_items['Item'] != '')]

        top_items = df_items['Item'].value_counts().reset_index()
        top_items.columns = ['Produit', 'Nombre de Commandes']
        
        col_p1, col_p2 = st.columns([1, 2])
        with col_p1:
            st.markdown("**📊 Top 15 Global**")
            st.dataframe(top_items.head(15), use_container_width=True, hide_index=True)
        with col_p2:
            fig_items = px.bar(top_items.head(10), x='Nombre de Commandes', y='Produit', orientation='h', title="Top 10 Produits", color_discrete_sequence=['#2ecc71'])
            fig_items.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_items, use_container_width=True)
            
        st.markdown("---")
        st.markdown("##### 📍 Top Produits par Ville")
        if 'city' in df_items.columns:
            city_items = df_items.groupby(['city', 'Item']).size().reset_index(name='Nombre')
            city_items = city_items.sort_values(['city', 'Nombre'], ascending=[True, False])
            top_city_items = city_items.groupby('city').head(5).reset_index(drop=True)
            st.dataframe(top_city_items, use_container_width=True, hide_index=True)
    else:
        st.warning("⚠️ La colonne 'Food Item' est introuvable.")

# ----------------------------------------
# ONGLET 9 : CATÉGORIES FOOD
# ----------------------------------------
with tabs[8]:
    st.markdown(f"#### 🍕 Performances des Catégories de Food ({semaine_selectionnee})")
    if 'Food Category' in df_current.columns:
        df_current['Food Category'] = df_current['Food Category'].astype(str).str.replace(r'\[|\]|/', '', regex=True).str.strip()
        df_current_cat = df_current[df_current['Food Category'] != 'nan']

        df_cat = compute_metrics(df_current_cat, ['Food Category'])
        df_cat['Success Rate'] = (df_cat['Delivered'] / df_cat['Requested'].replace(0, np.nan)).fillna(0)
        df_cat['AOV'] = (df_cat['GMV'] / df_cat['Delivered'].replace(0, np.nan)).fillna(0)
        
        df_cat_disp = df_cat.sort_values('Requested', ascending=False).copy()
        
        col_cat1, col_cat2 = st.columns(2)
        with col_cat1:
            fig_cat_req = px.pie(df_cat_disp.head(10), names='Food Category', values='Requested', title="Répartition par Volume", hole=0.4)
            st.plotly_chart(fig_cat_req, use_container_width=True)
        with col_cat2:
            fig_cat_gmv = px.bar(df_cat_disp.sort_values('GMV', ascending=False).head(10), x='Food Category', y='GMV', title="Top 10 Catégories (GMV)", color='Food Category')
            st.plotly_chart(fig_cat_gmv, use_container_width=True)
            
        st.markdown("**📋 Tableau Détaillé par Catégorie**")
        for c in ['Success Rate']: df_cat_disp[c] = df_cat_disp[c].apply(lambda x: f"{x:.1%}")
        for c in ['GMV', 'AOV']: df_cat_disp[c] = df_cat_disp[c].apply(lambda x: f"{x:,.0f} MAD")
        
        st.dataframe(df_cat_disp[['Food Category', 'Requested', 'Delivered', 'Success Rate', 'GMV', 'AOV']], use_container_width=True, hide_index=True)
    else:
        st.warning("⚠️ La colonne 'Food Category' est introuvable.")
