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

if "auth" not in st.session_state: st.session_state.auth = False
if "popup_entity_id" not in st.session_state: st.session_state.popup_entity_id = None
if "popup_entity_name" not in st.session_state: st.session_state.popup_entity_name = None
if "popup_entity_type" not in st.session_state: st.session_state.popup_entity_type = None

if not st.session_state.auth:
    st.title("🔒 Accès Sécurisé - Control Tower")
    with st.form("login_form"):
        username = st.text_input("Identifiant")
        password = st.text_input("Mot de passe", type="password")
        if st.form_submit_button("Se connecter"):
            secrets_pass = st.secrets.get("passwords", {})
            if username.lower() in secrets_pass and secrets_pass[username.lower()] == password:
                st.session_state.auth = True
                st.session_state.user = username.capitalize()
                st.rerun()
            else: st.error("❌ Identifiant ou mot de passe incorrect.")
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
        return build('drive', 'v3', credentials=creds), gspread.authorize(creds)
    except:
        st.error("❌ Erreur de connexion aux services Google.")
        st.stop()

drive_service, gc = get_google_clients()

def load_crm_data():
    try:
        sheet = gc.open("CRM_Yassir")
        pipe_records = sheet.worksheet("Pipelines").get_all_records()
        df_pipe = pd.DataFrame(pipe_records) if pipe_records else pd.DataFrame(columns=['Restaurant ID', 'Restaurant Name', 'AM_Name'])
        notes_records = sheet.worksheet("Notes_Historique").get_all_records()
        df_notes = pd.DataFrame(notes_records) if notes_records else pd.DataFrame(columns=['Date', 'Restaurant ID', 'Auteur', 'Contenu'])
        return df_pipe, df_notes, sheet
    except:
        st.error("❌ Erreur lecture CRM_Yassir sur Google Drive.")
        st.stop()

df_pipeline_master, df_notes_master, crm_sheet = load_crm_data()

@st.cache_data(ttl=300)
def get_data_files():
    results = drive_service.files().list(q="mimeType='text/csv'", fields="files(id, name)").execute()
    data_files = []
    for f in results.get('files', []):
        if re.search(r'data week (\d+)_(\d{4})\.csv', f['name'], re.IGNORECASE): data_files.append(f)
    return data_files

fichiers_disponibles = get_data_files()
if not fichiers_disponibles:
    st.warning("⚠️ Aucun fichier trouvé sur Drive.")
    st.stop()

# ==========================================
# 3. MOTEUR DE FUSION TOTALE DES FICHIERS
# ==========================================
@st.cache_data(show_spinner=False)
# ==========================================
# 3. MOTEUR DE FUSION TOTALE DES FICHIERS
# ==========================================
@st.cache_data(show_spinner=False)
def load_all_drive_csvs(files):
    dfs = []
    for f in files:
        req = drive_service.files().get_media(fileId=f['id'])
        fh = io.BytesIO()  # CORRECTION : On utilise bien le MÊME fichier virtuel
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done: 
            _, done = downloader.next_chunk()
        fh.seek(0)
        
        try:
            df = pd.read_csv(fh)
            if not df.empty:
                if "restaurant name" in df.columns: 
                    df.rename(columns={"restaurant name": "Restaurant Name"}, inplace=True)
                dfs.append(df)
        except pd.errors.EmptyDataError:
            pass # CORRECTION : Si un fichier sur Drive est vide, on l'ignore sans crasher
            
    return pd.concat(dfs, ignore_index=True).drop_duplicates(subset=['order id']) if dfs else pd.DataFrame()

col_am, col_info = st.columns([1, 2])
with col_am: am_choisi = st.selectbox("🎯 Sélection de la Pipeline", ["Global", "Houda", "Chaima", "Najwa", "Imane"])
with col_info: st.info(f"🔄 Fusion automatique activée ({len(fichiers_disponibles)} fichiers d'historique consolidés)")

try:
    with st.spinner("Aspiration et fusion de tout l'historique en cours..."):
        df_merged_full = load_all_drive_csvs(fichiers_disponibles)
        
        if am_choisi != "Global":
            df_pipe_am = df_pipeline_master[df_pipeline_master['AM_Name'].str.lower() == am_choisi.lower()]
            liste_attendue = df_pipe_am[['Restaurant ID', 'Restaurant Name']].drop_duplicates()
            df_merged = df_merged_full[df_merged_full['Restaurant ID'].isin(liste_attendue['Restaurant ID'])].copy()
        else:
            liste_data = df_merged_full[['Restaurant ID', 'Restaurant Name']].dropna().drop_duplicates(subset=['Restaurant ID'])
            liste_attendue = pd.concat([df_pipeline_master[['Restaurant ID', 'Restaurant Name']], liste_data]).drop_duplicates(subset=['Restaurant ID'])
            df_merged = df_merged_full.copy()

        pattern_exclus = '|'.join(['test', 'restau fixe', 'restau avance'])
        df_merged = df_merged[~df_merged['Restaurant Name'].astype(str).str.contains(pattern_exclus, case=False, na=False)]
        liste_attendue = liste_attendue[~liste_attendue['Restaurant Name'].astype(str).str.contains(pattern_exclus, case=False, na=False)]

        try: df_caisse = pd.read_csv("CaisseMA.csv", sep=None, engine='python')
        except: df_caisse = pd.DataFrame(columns=['Restaurant ID', 'Restaurant Name'])
        try: df_new = pd.read_csv("NewRestaurants.csv", sep=None, engine='python')
        except: df_new = pd.DataFrame(columns=['Restaurant ID', 'Restaurant Name'])

        df_merged['order day'] = pd.to_datetime(df_merged['order day'])
        df_merged['Week'] = "Week " + df_merged['order day'].dt.isocalendar().week.astype(str).str.zfill(2)
        semaines_dispos = sorted(df_merged['Week'].unique(), reverse=True)

except Exception as e:
    st.error(f"❌ Erreur critique lors de la fusion : {e}")
    st.stop()

with st.sidebar:
    st.markdown("### 📅 Filtres Temporels")
    semaine_selectionnee = st.selectbox("Semaine principale", semaines_dispos)
    try: semaine_precedente = semaines_dispos[semaines_dispos.index(semaine_selectionnee) + 1]
    except: semaine_precedente = None
    st.markdown("---")
    st.success(f"**Périmètre :** {am_choisi}")
    st.info(f"**Commandes totales (Historique) :** {len(df_merged):,}")

# ==========================================
# 4. MOTEUR DE CALCULS & PROTECTION ZERO
# ==========================================
def compute_metrics(df_subset, group_cols):
    return df_subset.groupby(group_cols).agg(
        Requested=('order id', 'count'), Delivered=('status', lambda x: (x == 'Delivered').sum()),
        Auto_Accepted=('Accepted By', lambda x: x.str.contains('restaurant', case=False, na=False).sum() if 'Accepted By' in df_subset.columns else 0),
        CancelledByRestaurant=('status', lambda x: x.str.contains('restaurant', case=False, na=False).sum()),
        GMV=('item total', lambda x: x[df_subset.loc[x.index, 'status'] == 'Delivered'].sum()),
        CA=('admin earnings', lambda x: x[df_subset.loc[x.index, 'status'] == 'Delivered'].sum()),
        Commission=('restaurant commission', lambda x: x[df_subset.loc[x.index, 'status'] == 'Delivered'].sum()),
        Promo_Restaurant=('coupon restaurant', 'sum'), Promo_Admin=('coupon admin', 'sum'),
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
    
    # NOUVEAU : Calculs WoW sur les Requests (Commandes Reçues)
    df_comp['wow Req'] = df_comp['Requested'] - df_comp['Requested_prev']
    df_comp['wow Req %'] = (df_comp['Requested'] / req_prev_safe - 1).fillna(0)
    
    df_comp['wow delivered'] = df_comp['Delivered'] - df_comp['Delivered_prev']
    df_comp['wow delivered %'] = (df_comp['Delivered'] / del_prev_safe - 1).fillna(0)
    df_comp['wow GMV'] = df_comp['GMV'] - df_comp['GMV_prev']
    df_comp['wow GMV %'] = (df_comp['GMV'] / gmv_prev_safe - 1).fillna(0)
    df_comp['wow T.A'] = df_comp['Taux Acceptation'] - (df_comp['Auto_Accepted_prev'] / req_prev_safe).fillna(0)
    df_comp['wow Cancellation'] = df_comp['Taux Cancellation'] - (df_comp['CancelledByRestaurant_prev'] / req_prev_safe).fillna(0)
    df_comp['Wow CA'] = df_comp['CA'] - df_comp['CA_prev']
    df_comp['Wow AOV'] = df_comp['AOV'] - (df_comp['GMV_prev'] / del_prev_safe).fillna(0)
    
    if not df_comp.empty and 'GMV' in df_comp.columns:
        if len(df_comp) >= 3: df_comp['Tier'] = pd.qcut(df_comp['GMV'].rank(method='first'), q=[0, 0.4, 0.8, 1.0], labels=['Tier C', 'Tier B', 'Tier A'])
        else: df_comp['Tier'] = 'Non classé'
    else: df_comp['Tier'] = "N/A"
    return df_comp

df_current = df_merged[df_merged['Week'] == semaine_selectionnee].copy()
df_prev = df_merged[df_merged['Week'] == semaine_precedente] if semaine_precedente else pd.DataFrame(columns=df_merged.columns)

def get_metrics_with_zeroes(df_subset, expected_base):
    metrics = compute_metrics(df_subset, ['Restaurant ID'])
    res = pd.merge(expected_base, metrics, on='Restaurant ID', how='left').fillna(0)
    return res

mapping_area = df_merged[['Restaurant ID', 'Area', 'city']].dropna().drop_duplicates('Restaurant ID')
liste_base_overview = pd.merge(liste_attendue, mapping_area, on='Restaurant ID', how='left')
liste_base_overview['Area'] = liste_base_overview['Area'].fillna('Aucune Cmd')
liste_base_overview['city'] = liste_base_overview['city'].fillna('Inconnu')

df_current_full = get_metrics_with_zeroes(df_current, liste_base_overview)
df_prev_full = get_metrics_with_zeroes(df_prev, liste_base_overview)

# ==========================================
# 5. POPUP 360° UNIVERSEL (RESTO, WEEK, FOOD)
# ==========================================
@st.dialog("🔍 Vue 360° Détaillée", width="large")
def popup_360(entity_type, entity_id, entity_name):
    # --- 1. FILTRAGE SELON LE TYPE D'ENTITÉ ---
    if entity_type == 'Restaurant':
        df_r = df_merged[df_merged['Restaurant ID'].astype(str) == str(entity_id)].sort_values('order day')
        note_id = str(entity_id)
    elif entity_type == 'Category':
        df_r = df_merged[df_merged['Food Category'].astype(str).str.replace(r'\[|\]|/', '', regex=True).str.strip() == str(entity_id)].sort_values('order day')
        note_id = f"Cat_{entity_id}"
    elif entity_type == 'Item':
        df_r = df_merged[df_merged['Food Item'].astype(str).str.contains(str(entity_id), regex=False, na=False)].sort_values('order day')
        note_id = f"Item_{entity_id}"
    elif entity_type == 'Week':
        df_r = df_merged.sort_values('order day') # Pour une semaine, on prend tout pour comparer
        note_id = f"Week_{entity_id}"

    st.markdown(f"### {'🏪' if entity_type == 'Restaurant' else '📊'} {entity_name}")
    
    # --- 2. FILTRES TEMPORELS ---
    col_filtre, col_btn = st.columns([2, 1])
    if entity_type == 'Week':
        with col_filtre: st.info(f"Analyse figée sur la {entity_name}")
        c_df = df_r[df_r['Week'] == entity_id]
        weeks_list = sorted(df_r['Week'].unique(), reverse=True)
        try: p_week = weeks_list[weeks_list.index(entity_id) + 1]
        except: p_week = None
        p_df = df_r[df_r['Week'] == p_week] if p_week else pd.DataFrame(columns=df_r.columns)
        label_evo = "WoW"
        choix_periode = entity_name
    else:
        with col_filtre:
            choix_periode = st.radio("Filtre d'analyse :", ["WoW (Semaine Active)", "MoM (30 Derniers Jours)", "Historique Complet"], horizontal=True, key=f"radio_pop_{note_id}")
        max_d = df_r['order day'].max()
        if pd.isna(max_d): max_d = datetime.now()
        
        if choix_periode == "WoW (Semaine Active)":
            c_df = df_r[df_r['Week'] == semaine_selectionnee]
            p_df = df_r[df_r['Week'] == semaine_precedente] if semaine_precedente else pd.DataFrame(columns=df_r.columns)
            label_evo = "WoW"
        elif choix_periode == "MoM (30 Derniers Jours)":
            c_df = df_r[df_r['order day'] >= max_d - timedelta(days=30)]
            p_df = df_r[(df_r['order day'] >= max_d - timedelta(days=60)) & (df_r['order day'] < max_d - timedelta(days=30))]
            label_evo = "MoM"
        else:
            c_df = df_r
            p_df = pd.DataFrame(columns=df_r.columns)
            label_evo = "Global"

    # --- 3. MOTEUR DE CALCULS DES KPIs ---
    def calc_kpis(df):
        req = len(df)
        df_deliv = df[df['status'] == 'Delivered'].copy()
        deliv = len(df_deliv)
        gmv = df_deliv['item total'].sum() if 'item total' in df_deliv.columns else 0
        aov = (gmv / deliv) if deliv > 0 else 0
        p_admin = df_deliv['coupon admin'].sum() if 'coupon admin' in df_deliv.columns else 0
        p_resto = df_deliv['coupon restaurant'].sum() if 'coupon restaurant' in df_deliv.columns else 0
        sr = (deliv / req) if req > 0 else 0
        
        t_deliv = 0
        if 'delivery time(M)' in df_deliv.columns: t_deliv = df_deliv['delivery time(M)'].mean()
        elif 'delivery time' in df_deliv.columns: t_deliv = df_deliv['delivery time'].mean()
            
        t_prep = 0
        if 'preparation time' in df_deliv.columns: t_prep = df_deliv['preparation time'].mean()
        elif 'Ready by Restaurant' in df_deliv.columns and 'Accepted at' in df_deliv.columns:
            try:
                accepted = pd.to_datetime(df_deliv['Accepted at'].astype(str).str.replace(' /', ''), format='mixed', errors='coerce')
                ready = pd.to_datetime(df_deliv['Ready by Restaurant'].astype(str).str.replace(' /', ''), format='mixed', errors='coerce')
                t_prep = ((ready - accepted).dt.total_seconds() / 60).mean()
            except: t_prep = 0
        return req, deliv, gmv, aov, p_admin, p_resto, sr, t_prep, t_deliv

    c_req, c_del, c_gmv, c_aov, c_pa, c_pr, c_sr, c_prep, c_dt = calc_kpis(c_df)
    p_req, p_del, p_gmv, p_aov, p_pa, p_pr, p_sr, p_prep, p_dt = calc_kpis(p_df)

    def format_evo(curr, prev):
        if prev == 0 and curr > 0: return "+100%"
        if prev == 0 and curr == 0: return "-"
        return f"{(curr / prev) - 1:+.1%}"

    # --- 4. BOUTON DE RAPPORT ---
    with col_btn:
        report_text = f"📊 RAPPORT DE PERFORMANCES - {entity_name}\n"
        report_text += f"Période : {choix_periode}\n"
        report_text += f"----------------------------------------\n"
        report_text += f"📦 Reçues : {c_req} ({label_evo}: {format_evo(c_req, p_req)})\n"
        report_text += f"✅ Livrées : {c_del} ({label_evo}: {format_evo(c_del, p_del)})\n"
        report_text += f"🎯 Success Rate : {c_sr:.1%} ({label_evo}: {format_evo(c_sr, p_sr)})\n"
        report_text += f"💰 GMV : {c_gmv:,.0f} MAD ({label_evo}: {format_evo(c_gmv, p_gmv)})\n"
        report_text += f"🛒 Panier Moyen : {c_aov:,.0f} MAD ({label_evo}: {format_evo(c_aov, p_aov)})\n"
        report_text += f"----------------------------------------\n"
        st.download_button("📥 Télécharger Présentation", data=report_text, file_name=f"Report_{entity_name}.txt", mime="text/plain", use_container_width=True)

    st.markdown("---")
    
    # --- 5. BOXES VIOLETTES ---
    b1, b2, b3 = st.columns(3)
    with b1: st.markdown(f"<div class='purple-box'><h3>Commandes Reçues</h3><h2>{c_req}</h2><p>{label_evo}: {format_evo(c_req, p_req)}</p></div>", unsafe_allow_html=True)
    with b2: st.markdown(f"<div class='purple-box'><h3>Commandes Livrées</h3><h2>{c_del}</h2><p>{label_evo}: {format_evo(c_del, p_del)}</p></div>", unsafe_allow_html=True)
    with b3: st.markdown(f"<div class='purple-box'><h3>Success Rate</h3><h2>{c_sr:.1%}</h2><p>{label_evo}: {format_evo(c_sr, p_sr)}</p></div>", unsafe_allow_html=True)
    
    b4, b5, b6 = st.columns(3)
    with b4: st.markdown(f"<div class='purple-box'><h3>GMV Généré</h3><h2>{c_gmv:,.0f} MAD</h2><p>{label_evo}: {format_evo(c_gmv, p_gmv)}</p></div>", unsafe_allow_html=True)
    with b5: st.markdown(f"<div class='purple-box'><h3>Panier Moyen (AOV)</h3><h2>{c_aov:,.0f} MAD</h2><p>{label_evo}: {format_evo(c_aov, p_aov)}</p></div>", unsafe_allow_html=True)
    with b6: st.markdown(f"<div class='purple-box'><h3>Promos (Yassir / Resto)</h3><h2>{c_pa:,.0f} / {c_pr:,.0f}</h2><p>{label_evo}: {format_evo(c_pa, p_pa)} / {format_evo(c_pr, p_pr)}</p></div>", unsafe_allow_html=True)
    
    b7, b8, b9 = st.columns(3)
    v_prep = f"{c_prep:.0f} min" if pd.notnull(c_prep) and c_prep > 0 else "N/A"
    v_del = f"{c_dt:.0f} min" if pd.notnull(c_dt) and c_dt > 0 else "N/A"
    with b7: st.markdown(f"<div class='purple-box'><h3>Temps Préparation</h3><h2>{v_prep}</h2><p>{label_evo}: {format_evo(c_prep, p_prep) if v_prep != 'N/A' else '-'}</p></div>", unsafe_allow_html=True)
    with b8: st.markdown(f"<div class='purple-box'><h3>Temps Livraison</h3><h2>{v_del}</h2><p>{label_evo}: {format_evo(c_dt, p_dt) if v_del != 'N/A' else '-'}</p></div>", unsafe_allow_html=True)
    with b9: st.markdown(f"<div class='purple-box'><h3>Analyse Active</h3><h2>{label_evo}</h2><p>Période sélectionnée</p></div>", unsafe_allow_html=True)

    # --- 6. GRAPHIQUE ET TOP/FLOP (SI SEMAINE) ---
    if entity_type == 'Week':
        st.markdown("#### 📈 Tops & Flops de la Semaine (Accélération GMV)")
        resto_curr = compute_metrics(c_df, ['Restaurant ID', 'Restaurant Name'])
        resto_prev = compute_metrics(p_df, ['Restaurant ID', 'Restaurant Name'])
        comp_w = compare_wow(resto_curr, resto_prev, ['Restaurant ID', 'Restaurant Name'])
        
        c_t, c_f = st.columns(2)
        with c_t:
            st.success("🏆 Top 10 Accélérations")
            st.dataframe(comp_w.sort_values('wow Req', ascending=False).head(10)[['Restaurant Name', 'wow Req', 'wow Req %']].style.format({'wow Req': '{:,.0f}', 'wow Req %': '{:+.1%}'}), hide_index=True)
        with c_f:
            st.error("📉 Flop 10 Chutes")
            st.dataframe(comp_w.sort_values('wow Req', ascending=True).head(10)[['Restaurant Name', 'wow Req', 'wow Req %']].style.format({'wow Req': '{:,.0f}', 'wow Req %': '{:+.1%}'}), hide_index=True)

    if not c_df.empty or not p_df.empty:
        df_trend = c_df.groupby('order day').agg(Req=('order id','count'), Deliv=('status', lambda x: (x=='Delivered').sum())).reset_index()
        if not df_trend.empty:
            st.plotly_chart(px.line(df_trend, x='order day', y=['Req', 'Deliv'], title="Tendance Journalière (Période ciblée)", markers=True), use_container_width=True, key=f"chart_popup_{note_id}")
    
    st.markdown("---")
    
    # --- 7. NOTES ET SUIVI D'IMPACT ---
    col_act, col_trans = st.columns(2)
    with col_act:
        st.markdown(f"#### 📝 Ajouter une Note ({entity_name})")
        nouvelle_note = st.text_area("Description :", key=f"note_{note_id}")
        if st.button("💾 Enregistrer la note", key=f"btn_{note_id}"):
            ws_notes = crm_sheet.worksheet("Notes_Historique")
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            ws_notes.append_row([date_str, note_id, st.session_state.user, nouvelle_note])
            st.success("Note enregistrée ! Fermez pour actualiser.")

        st.markdown("#### 📜 Historique & Impact")
        notes_r = df_notes_master[df_notes_master['Restaurant ID'].astype(str) == note_id]
        if not notes_r.empty:
            for idx_n, row in notes_r.iterrows():
                with st.expander(f"📅 {row['Date']} par {row['Auteur']}"):
                    st.write(row['Contenu'])
                    jours = st.radio("Analyse post-action :", [7, 15, 30], format_func=lambda x: f"{x} Jours", horizontal=True, key=f"r_{idx_n}_{note_id}")
                    try:
                        d_note = pd.to_datetime(row['Date']).date()
                        # Si la note est sur une semaine complète, on compare sur tout le dataset, sinon sur l'entité filtrée
                        base_df = df_merged if entity_type == 'Week' else df_r
                        base_df['date_only'] = base_df['order day'].dt.date
                        avant = base_df[(base_df['date_only'] < d_note) & (base_df['date_only'] >= d_note - timedelta(days=jours))]
                        apres = base_df[(base_df['date_only'] >= d_note) & (base_df['date_only'] <= d_note + timedelta(days=jours))]
                        g_av = avant[avant['status'] == 'Delivered']['item total'].sum()
                        g_ap = apres[apres['status'] == 'Delivered']['item total'].sum()
                        e_ap = (g_ap / g_av - 1) if g_av > 0 else 0
                        st.info(f"📊 Impact ({jours}j) : GMV Avant = {g_av:,.0f} MAD | GMV Après = {g_ap:,.0f} MAD ({e_ap:+.1%})")
                    except: pass
        else: st.info("Aucune note pour cette entité.")

    with col_trans:
        if entity_type == 'Restaurant':
            st.markdown("#### 🔄 Transférer le restaurant")
            pipe_am = df_pipeline_master[df_pipeline_master['Restaurant ID'].astype(str) == str(entity_id)]
            current_am = pipe_am['AM_Name'].iloc[0] if not pipe_am.empty else "Global / Inconnu"
            st.write(f"Pipeline actuelle : **{current_am}**")
            nouveau_am = st.selectbox("Transférer vers :", ["Houda", "Chaima", "Najwa", "Imane"], key=f"t_{note_id}")
            if st.button("🚀 Valider le transfert", key=f"bt_t_{note_id}"):
                ws_pipe = crm_sheet.worksheet("Pipelines")
                try:
                    cell = ws_pipe.find(str(entity_id), in_column=1)
                    ws_pipe.update_cell(cell.row, 3, nouveau_am)
                except:
                    ws_pipe.append_row([str(entity_id), entity_name, nouveau_am])
                st.success(f"Transféré à {nouveau_am} !")


# ==========================================
# 6. ONGLETS ET AFFICHAGES VISUELS
# ==========================================
tabs = st.tabs(["🌍 1. Macro", "📈 2. Overview", "❌ 3. Annulations", "🤖 4. Auto", "💻 5. Caisse.ma", "✨ 6. New", "👻 7. Inactifs", "🏆 8. Héros", "🍕 9. Catégories"])

# ----------------------------------------
# ONGLET 1 : ANALYSE GLOBAL (MACRO)
# ----------------------------------------
with tabs[0]:
    st.markdown("#### 🌍 Analyse Macro des Performances (🖱️ Cliquez sur une semaine)")
    vue_temporelle = st.radio("Sélectionnez la vue globale :", ["📊 Par Semaine", "📅 Par Jour"], horizontal=True, key="macro_vue_temporelle")
    df_macro_base = df_merged.copy()
    df_macro_base['Période'] = df_macro_base['order day'].dt.strftime('%Y-%m-%d') if vue_temporelle == "📅 Par Jour" else df_macro_base['Week']

    df_macro = df_macro_base.groupby('Période').agg(
        Reçu=('order id', 'count'), Livré=('status', lambda x: (x == 'Delivered').sum()),
        GMV=('item total', lambda x: x[df_macro_base.loc[x.index, 'status'] == 'Delivered'].sum()),
        CA=('admin earnings', lambda x: x[df_macro_base.loc[x.index, 'status'] == 'Delivered'].sum())
    ).reset_index()

    df_macro['AOV'] = (df_macro['GMV'] / df_macro['Livré'].replace(0, np.nan)).fillna(0)
    df_macro = df_macro.sort_values(by='Période', ascending=True)

    for col in ['Reçu', 'Livré', 'GMV', 'CA', 'AOV']: df_macro[f'V. {col}'] = df_macro[col].pct_change()
    df_macro_display = df_macro.sort_values(by='Période', ascending=False).copy()
    for col in ['V. Reçu', 'V. Livré', 'V. GMV', 'V. CA', 'V. AOV']: df_macro_display[col] = df_macro_display[col].apply(lambda x: f"{x:+.1%}" if pd.notnull(x) else "-")
    for col in ['GMV', 'CA', 'AOV']: df_macro_display[col] = df_macro_display[col].apply(lambda x: f"{x:,.2f}")

    disp_macro = df_macro_display[['Période', 'Reçu', 'Livré', 'GMV', 'CA', 'AOV', 'V. Reçu', 'V. Livré', 'V. GMV', 'V. CA', 'V. AOV']]
    ev_macro = st.dataframe(disp_macro, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
    
    if ev_macro.selection.rows:
        idx = ev_macro.selection.rows[0]
        if "Week" in str(disp_macro.iloc[idx]['Période']):
            st.session_state.popup_entity_type = 'Week'
            st.session_state.popup_entity_id = disp_macro.iloc[idx]['Période']
            st.session_state.popup_entity_name = disp_macro.iloc[idx]['Période']

    st.markdown("---")
    df_daily = compute_metrics(df_merged, ['order day']).sort_values('order day')
    col_g1, col_g2 = st.columns(2)
with col_g1: st.plotly_chart(px.line(df_daily, x="order day", y="GMV", title="Tendance GMV", markers=True), use_container_width=True, key="macro_gmv_chart")
with col_g2: st.plotly_chart(px.line(df_daily, x="order day", y="Requested", title="Tendance Commandes Reçues", markers=True, color_discrete_sequence=['#f39c12']), use_container_width=True, key="macro_req_chart")

# ----------------------------------------
# ONGLET 2 : OVERVIEW PIPELINE
# ----------------------------------------
with tabs[1]:
    st.markdown("#### 📋 Base Détaillée (🖱️ Cliquez sur une ligne)")
    resto_comp = compare_wow(df_current_full, df_prev_full, ['Restaurant ID', 'Restaurant Name', 'Area'])
    
    cols = ['Restaurant ID', 'Tier', 'Area', 'Restaurant Name', 'Requested', 'Delivered', 'Success Rate', 'Taux Acceptation', 'wow T.A', 'GMV', 'wow GMV %']
    df_disp = resto_comp[cols].copy()
    for c in ['Success Rate', 'Taux Acceptation', 'wow T.A', 'wow GMV %']: df_disp[c] = df_disp[c].apply(lambda x: f"{x:+.1%}")
    for c in ['GMV']: df_disp[c] = df_disp[c].apply(lambda x: f"{x:,.0f}")

    event = st.dataframe(df_disp, column_config={"Restaurant ID": None}, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
    if event.selection.rows:
        st.session_state.popup_entity_type = 'Restaurant'
        st.session_state.popup_entity_id = df_disp.iloc[event.selection.rows[0]]['Restaurant ID']
        st.session_state.popup_entity_name = df_disp.iloc[event.selection.rows[0]]['Restaurant Name']

# ----------------------------------------
# ONGLET 3 ET 4 : ANNULATIONS & AUTO
# ----------------------------------------
with tabs[2]:
    st.markdown("#### ❌ Surveillance des Annulations")
    df_canc_curr = df_current[df_current['status'].str.contains('Cancelled', case=False, na=False)]
    if not df_canc_curr.empty:
        reasons = df_canc_curr['cancellation reason '].value_counts().reset_index()
        reasons.columns = ['Motif', 'Nombre']
        st.plotly_chart(px.pie(reasons, names='Motif', values='Nombre', hole=0.4), use_container_width=True)

with tabs[3]:
    st.markdown("#### 🤖 Automatisation")
    if 'Accepted By' in df_current.columns:
        df_current['Is_Auto'] = df_current['Accepted By'].str.contains('restaurant', case=False, na=False)
        auto_r = df_current.groupby('Is_Auto').agg(Req=('order id', 'count'), Del=('status', lambda x: (x == 'Delivered').sum()), GMV=('item total', lambda x: x[df_current.loc[x.index, 'status'] == 'Delivered'].sum())).reset_index()
        auto_r['Type'] = auto_r['Is_Auto'].map({True: '🤖 Automatisé', False: '👨‍💻 Manuel'})
        auto_r['Success Rate'] = (auto_r['Del'] / auto_r['Req']).fillna(0)
        st.dataframe(auto_r[['Type', 'Req', 'Del', 'Success Rate', 'GMV']].style.format({'Success Rate': '{:.1%}', 'GMV': '{:,.0f}'}), hide_index=True)

def merge_ext(df_ext, comp):
    res = pd.merge(pd.merge(df_ext[['Restaurant ID']], liste_attendue, on='Restaurant ID', how='inner'), comp.drop(columns=['Restaurant Name'], errors='ignore'), on='Restaurant ID', how='left')
    for m in ['Requested', 'Delivered', 'GMV', 'wow GMV', 'wow GMV %', 'Success Rate', 'Taux Acceptation', 'wow delivered %']:
        if m in res.columns: res[m] = res[m].fillna(0)
    return res

# ----------------------------------------
# ONGLETS 5, 6, 7 : Caisse, New, Inactifs
# ----------------------------------------
with tabs[4]:
    st.markdown("#### 💻 Caisse.ma (🖱️ Cliquable)")
    if not df_caisse.empty:
        df_c_comp = merge_ext(df_caisse, resto_comp)
        if not df_c_comp.empty: 
            disp_caisse = df_c_comp[['Restaurant ID', 'Restaurant Name', 'Requested', 'GMV', 'wow GMV %', 'Success Rate']].copy()
            ev_c = st.dataframe(disp_caisse.style.format({'GMV': '{:,.0f}', 'wow GMV %': '{:+.1%}', 'Success Rate': '{:.1%}'}), column_config={"Restaurant ID": None}, hide_index=True, on_select="rerun", selection_mode="single-row")
            if ev_c.selection.rows:
                st.session_state.popup_entity_type = 'Restaurant'
                st.session_state.popup_entity_id = disp_caisse.iloc[ev_c.selection.rows[0]]['Restaurant ID']
                st.session_state.popup_entity_name = disp_caisse.iloc[ev_c.selection.rows[0]]['Restaurant Name']

with tabs[5]:
    st.markdown("#### ✨ New Restaurants (🖱️ Cliquable)")
    if not df_new.empty:
        df_n_comp = merge_ext(df_new, resto_comp)
        if not df_n_comp.empty: 
            disp_new = df_n_comp[['Restaurant ID', 'Restaurant Name', 'Requested', 'GMV', 'Success Rate']].copy()
            ev_n = st.dataframe(disp_new.style.format({'GMV': '{:,.0f}', 'Success Rate': '{:.1%}'}), column_config={"Restaurant ID": None}, hide_index=True, on_select="rerun", selection_mode="single-row")
            if ev_n.selection.rows:
                st.session_state.popup_entity_type = 'Restaurant'
                st.session_state.popup_entity_id = disp_new.iloc[ev_n.selection.rows[0]]['Restaurant ID']
                st.session_state.popup_entity_name = disp_new.iloc[ev_n.selection.rows[0]]['Restaurant Name']

with tabs[6]:
    st.markdown("#### 👻 Inactifs")
    j_inactifs = st.radio("Signaler les inactifs depuis :", [3, 7, 15, 30], format_func=lambda x: f"{x} Jours", horizontal=True, key="inactifs_jours_radio")
    max_d = df_merged['order day'].max()
    restos_actifs = df_merged[df_merged['order day'] >= max_d - timedelta(days=j_inactifs)]['Restaurant ID'].unique()
    restos_inactifs = liste_attendue[~liste_attendue['Restaurant ID'].isin(restos_actifs)]
    st.error(f"⚠️ {len(restos_inactifs)} restaurants inactifs depuis {j_inactifs} jours")
    st.dataframe(restos_inactifs[['Restaurant Name']], hide_index=True)

# ----------------------------------------
# ONGLETS 8 & 9 : Héros & Catégories (MAINTENANT CLIQUABLES)
# ----------------------------------------
with tabs[7]:
    st.markdown("#### 🏆 Produits Héros (🖱️ Cliquable)")
    if 'Food Item' in df_current.columns:
        df_items = df_current.assign(Item=df_current['Food Item'].astype(str).str.replace(r'\[|\]|\{\d+\}', '', regex=True).str.split(',')).explode('Item')
        df_items['Item'] = df_items['Item'].str.strip()
        df_items = df_items[(df_items['Item'] != 'nan') & (df_items['Item'] != '')]
        top_items = df_items['Item'].value_counts().reset_index()
        top_items.columns = ['Produit', 'Nombre']
        
        c_p1, c_p2 = st.columns([1, 2])
        with c_p1: 
            ev_p = st.dataframe(top_items.head(15), hide_index=True, on_select="rerun", selection_mode="single-row")
            if ev_p.selection.rows:
                st.session_state.popup_entity_type = 'Item'
                st.session_state.popup_entity_id = top_items.iloc[ev_p.selection.rows[0]]['Produit']
                st.session_state.popup_entity_name = top_items.iloc[ev_p.selection.rows[0]]['Produit']
        with c_p2: st.plotly_chart(px.bar(top_items.head(10), x='Nombre', y='Produit', orientation='h').update_layout(yaxis={'categoryorder':'total ascending'}), use_container_width=True)

with tabs[8]:
    st.markdown("#### 🍕 Catégories Food (🖱️ Cliquable)")
    if 'Food Category' in df_current.columns:
        df_current_cat = df_current[df_current['Food Category'].astype(str) != 'nan'].copy()
        df_current_cat['Food Category'] = df_current_cat['Food Category'].astype(str).str.replace(r'\[|\]|/', '', regex=True).str.strip()
        df_cat = compute_metrics(df_current_cat, ['Food Category'])
        df_cat['Success Rate'] = (df_cat['Delivered'] / df_cat['Requested'].replace(0, np.nan)).fillna(0)
        df_cat['AOV'] = (df_cat['GMV'] / df_cat['Delivered'].replace(0, np.nan)).fillna(0)
        
        df_cat_disp = df_cat.sort_values('Requested', ascending=False)
        disp_cat = df_cat_disp[['Food Category', 'Requested', 'Delivered', 'Success Rate', 'GMV', 'AOV']].copy()
        
        ev_cat = st.dataframe(disp_cat.style.format({'Success Rate': '{:.1%}', 'GMV': '{:,.0f}', 'AOV': '{:,.0f}'}), hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row")
        if ev_cat.selection.rows:
            st.session_state.popup_entity_type = 'Category'
            st.session_state.popup_entity_id = disp_cat.iloc[ev_cat.selection.rows[0]]['Food Category']
            st.session_state.popup_entity_name = disp_cat.iloc[ev_cat.selection.rows[0]]['Food Category']


# ==========================================
# GESTION SÉCURISÉE DU POPUP (FIN DU FICHIER)
# ==========================================
if st.session_state.get("popup_entity_id") is not None:
    popup_360(st.session_state.popup_entity_type, st.session_state.popup_entity_id, st.session_state.popup_entity_name)
    # On vide la mémoire pour éviter que le popup s'ouvre en boucle et fasse l'erreur "Duplicate Element ID"
    st.session_state.popup_entity_id = None
    st.session_state.popup_entity_type = None
    st.session_state.popup_entity_name = None

# ----------------------------------------
# ONGLET 2 : OVERVIEW PIPELINE
# ----------------------------------------
with tabs[1]:
    st.markdown("#### 📋 Base Détaillée (🖱️ Cliquez sur une ligne pour ouvrir le CRM)")
    resto_comp = compare_wow(df_current_full, df_prev_full, ['Restaurant ID', 'Restaurant Name', 'Area'])
    
    cols = ['Restaurant ID', 'Tier', 'Area', 'Restaurant Name', 'Requested', 'Delivered', 'Success Rate', 'Taux Acceptation', 'wow T.A', 'GMV', 'wow GMV %']
    df_disp = resto_comp[cols].copy()
    for c in ['Success Rate', 'Taux Acceptation', 'wow T.A', 'wow GMV %']: df_disp[c] = df_disp[c].apply(lambda x: f"{x:+.1%}")
    for c in ['GMV']: df_disp[c] = df_disp[c].apply(lambda x: f"{x:,.0f}")

    event = st.dataframe(df_disp, column_config={"Restaurant ID": None}, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
    if event.selection.rows:
        st.session_state.popup_resto_id = df_disp.iloc[event.selection.rows[0]]['Restaurant ID']
        st.session_state.popup_resto_name = df_disp.iloc[event.selection.rows[0]]['Restaurant Name']

    anomalies = resto_comp[(resto_comp['Tier'] == 'Tier A') & (resto_comp['wow delivered %'] < -0.15)]
    if not anomalies.empty:
        st.error(f"🚨 **ALERTE BUSINESS :** {len(anomalies)} restaurants du 'Tier A' ont subi une baisse de plus de 15% WoW !")
        st.dataframe(anomalies[['Restaurant Name', 'Area', 'Requested', 'wow delivered %', 'wow GMV %']].style.format({'wow delivered %': '{:+.1%}', 'wow GMV %': '{:+.1%}'}), hide_index=True)

    st.markdown("#### 📈 Tops & Flops")
    col_t, col_f = st.columns(2)
    with col_t: st.success("🏆 **Top 30 Accélérations**"); st.dataframe(resto_comp.sort_values('wow delivered', ascending=False).head(30)[['Restaurant Name', 'Tier', 'wow delivered %']].style.format({'wow delivered %': '{:+.1%}'}), hide_index=True)
    with col_f: st.error("📉 **Flop 30 Chutes**"); st.dataframe(resto_comp.sort_values('wow delivered', ascending=True).head(30)[['Restaurant Name', 'Tier', 'wow delivered %']].style.format({'wow delivered %': '{:+.1%}'}), hide_index=True)

# ----------------------------------------
# ONGLET 3 : ANNULATIONS
# ----------------------------------------
with tabs[2]:
    st.markdown("#### ❌ Surveillance des Annulations")
    df_canc_curr = df_current[df_current['status'].str.contains('Cancelled', case=False, na=False)]
    
    col_c1, col_c2 = st.columns([1, 2])
    with col_c1:
        st.markdown("**Comparatif par Area**")
        if 'Area' in df_canc_curr.columns:
            canc_area = df_canc_curr.groupby('Area').size().reset_index(name='Annulations')
            m_area = pd.merge(canc_area, df_current.groupby('Area').size().reset_index(name='Total Req'), on='Area')
            m_area['% Cancel'] = m_area['Annulations'] / m_area['Total Req']
            st.dataframe(m_area.sort_values('% Cancel', ascending=False).head(10).style.format({'% Cancel': '{:.1%}'}), hide_index=True)
            
    with col_c2:
        st.markdown("**Motifs d'Annulations**")
        if not df_canc_curr.empty:
            reasons = df_canc_curr['cancellation reason '].value_counts().reset_index()
            reasons.columns = ['Motif', 'Nombre']
            st.plotly_chart(px.pie(reasons, names='Motif', values='Nombre', hole=0.4), use_container_width=True, key="canc_pie_chart")

    st.markdown("#### 🚨 Les Récidivistes")
    pires = resto_comp[resto_comp['Requested'] > 5].sort_values('Taux Cancellation', ascending=False).head(15)
    st.dataframe(pires[['Restaurant Name', 'Area', 'Requested', 'CancelledByRestaurant', 'Taux Cancellation', 'wow Cancellation']].style.format({'Taux Cancellation': '{:.1%}', 'wow Cancellation': '{:+.1%}'}), hide_index=True)

# ----------------------------------------
# ONGLET 4 : AUTOMATION
# ----------------------------------------
with tabs[3]:
    st.markdown("#### 🤖 Automatisation")
    if 'Accepted By' in df_current.columns:
        df_current['Is_Auto'] = df_current['Accepted By'].str.contains('restaurant', case=False, na=False)
        auto_r = df_current.groupby('Is_Auto').agg(Req=('order id', 'count'), Del=('status', lambda x: (x == 'Delivered').sum()), GMV=('item total', lambda x: x[df_current.loc[x.index, 'status'] == 'Delivered'].sum())).reset_index()
        auto_r['Type'] = auto_r['Is_Auto'].map({True: '🤖 Automatisé', False: '👨‍💻 Manuel'})
        auto_r['Success Rate'] = (auto_r['Del'] / auto_r['Req']).fillna(0)
        st.dataframe(auto_r[['Type', 'Req', 'Del', 'Success Rate', 'GMV']].style.format({'Success Rate': '{:.1%}', 'GMV': '{:,.0f}'}), hide_index=True)
    
    st.markdown("---")
    col_acc, col_reg = st.columns(2)
    with col_acc: st.success("**🚀 Accélérations**"); st.dataframe(resto_comp[resto_comp['wow T.A'] > 0].sort_values('wow T.A', ascending=False).head(10)[['Restaurant Name', 'Requested', 'Taux Acceptation', 'wow T.A']].style.format({'Taux Acceptation': '{:.1%}', 'wow T.A': '{:+.1%}'}), hide_index=True)
    with col_reg: st.error("**⚠️ Régressions**"); st.dataframe(resto_comp[resto_comp['wow T.A'] < 0].sort_values('wow T.A', ascending=True).head(10)[['Restaurant Name', 'Requested', 'Taux Acceptation', 'wow T.A']].style.format({'Taux Acceptation': '{:.1%}', 'wow T.A': '{:+.1%}'}), hide_index=True)

def merge_ext(df_ext, comp):
    res = pd.merge(pd.merge(df_ext[['Restaurant ID']], liste_attendue, on='Restaurant ID', how='inner'), comp.drop(columns=['Restaurant Name'], errors='ignore'), on='Restaurant ID', how='left')
    for m in ['Requested', 'Delivered', 'GMV', 'wow GMV', 'wow GMV %', 'Success Rate', 'Taux Acceptation', 'wow delivered %']:
        if m in res.columns: res[m] = res[m].fillna(0)
    return res

# ----------------------------------------
# ONGLETS 5, 6, 7 : Caisse, New, Inactifs
# ----------------------------------------
with tabs[4]:
    st.markdown("#### 💻 Caisse.ma (🖱️ Cliquable)")
    if not df_caisse.empty:
        df_c_comp = merge_ext(df_caisse, resto_comp)
        if not df_c_comp.empty: 
            ev_c = st.dataframe(df_c_comp[['Restaurant ID', 'Restaurant Name', 'Requested', 'GMV', 'wow GMV %', 'Success Rate']].style.format({'GMV': '{:,.0f}', 'wow GMV %': '{:+.1%}', 'Success Rate': '{:.1%}'}), column_config={"Restaurant ID": None}, hide_index=True, on_select="rerun", selection_mode="single-row")
            if ev_c.selection.rows: 
                st.session_state.popup_resto_id = df_c_comp.iloc[ev_c.selection.rows[0]]['Restaurant ID']
                st.session_state.popup_resto_name = df_c_comp.iloc[ev_c.selection.rows[0]]['Restaurant Name']

with tabs[5]:
    st.markdown("#### ✨ New Restaurants (🖱️ Cliquable)")
    if not df_new.empty:
        df_n_comp = merge_ext(df_new, resto_comp)
        if not df_n_comp.empty: 
            ev_n = st.dataframe(df_n_comp[['Restaurant ID', 'Restaurant Name', 'Requested', 'GMV', 'Success Rate']].style.format({'GMV': '{:,.0f}', 'Success Rate': '{:.1%}'}), column_config={"Restaurant ID": None}, hide_index=True, on_select="rerun", selection_mode="single-row")
            if ev_n.selection.rows: 
                st.session_state.popup_resto_id = df_n_comp.iloc[ev_n.selection.rows[0]]['Restaurant ID']
                st.session_state.popup_resto_name = df_n_comp.iloc[ev_n.selection.rows[0]]['Restaurant Name']

with tabs[6]:
    st.markdown("#### 👻 Inactifs")
    j_inactifs = st.radio("Signaler les inactifs depuis :", [3, 7, 15, 30], format_func=lambda x: f"{x} Jours", horizontal=True)
    max_d = df_merged['order day'].max()
    restos_actifs = df_merged[df_merged['order day'] >= max_d - timedelta(days=j_inactifs)]['Restaurant ID'].unique()
    restos_inactifs = liste_attendue[~liste_attendue['Restaurant ID'].isin(restos_actifs)]
    st.error(f"⚠️ {len(restos_inactifs)} restaurants inactifs depuis {j_inactifs} jours")
    st.dataframe(restos_inactifs[['Restaurant Name']], hide_index=True)

# ----------------------------------------
# ONGLETS 8 & 9 : Héros & Catégories
# ----------------------------------------
with tabs[7]:
    st.markdown("#### 🏆 Produits Héros")
    if 'Food Item' in df_current.columns:
        df_items = df_current.assign(Item=df_current['Food Item'].astype(str).str.replace(r'\[|\]|\{\d+\}', '', regex=True).str.split(',')).explode('Item')
        df_items['Item'] = df_items['Item'].str.strip()
        df_items = df_items[(df_items['Item'] != 'nan') & (df_items['Item'] != '')]
        top_items = df_items['Item'].value_counts().reset_index()
        top_items.columns = ['Produit', 'Nombre']
        
        c_p1, c_p2 = st.columns([1, 2])
        with c_p1: st.dataframe(top_items.head(15), hide_index=True)
        with c_p2: st.plotly_chart(px.bar(top_items.head(10), x='Nombre', y='Produit', orientation='h', title="Top 10 Global").update_layout(yaxis={'categoryorder':'total ascending'}), use_container_width=True)
        
        st.markdown("##### 📍 Top Produits par Ville")
        if 'city' in df_items.columns:
            city_items = df_items.groupby(['city', 'Item']).size().reset_index(name='Nombre').sort_values(['city', 'Nombre'], ascending=[True, False])
            st.dataframe(city_items.groupby('city').head(5).reset_index(drop=True), hide_index=True)

with tabs[8]:
    st.markdown("#### 🍕 Catégories Food")
    if 'Food Category' in df_current.columns:
        df_current_cat = df_current[df_current['Food Category'].astype(str) != 'nan'].copy()
        df_current_cat['Food Category'] = df_current_cat['Food Category'].astype(str).str.replace(r'\[|\]|/', '', regex=True).str.strip()
        df_cat = compute_metrics(df_current_cat, ['Food Category'])
        df_cat['Success Rate'] = (df_cat['Delivered'] / df_cat['Requested'].replace(0, np.nan)).fillna(0)
        df_cat['AOV'] = (df_cat['GMV'] / df_cat['Delivered'].replace(0, np.nan)).fillna(0)
        
        df_cat_disp = df_cat.sort_values('Requested', ascending=False)
        c_c1, c_c2 = st.columns(2)
        with c_c1: st.plotly_chart(px.pie(df_cat_disp.head(10), names='Food Category', values='Requested', hole=0.4))
        with c_c2: st.plotly_chart(px.bar(df_cat_disp.sort_values('GMV', ascending=False).head(10), x='Food Category', y='GMV'))
        
        st.dataframe(df_cat_disp[['Food Category', 'Requested', 'Delivered', 'Success Rate', 'GMV', 'AOV']].style.format({'Success Rate': '{:.1%}', 'GMV': '{:,.0f}', 'AOV': '{:,.0f}'}), hide_index=True, use_container_width=True)

# ==========================================
# GESTION SÉCURISÉE DU POPUP (Fin du fichier)
# ==========================================
if st.session_state.get("popup_resto_id") is not None:
    popup_restaurant(st.session_state.popup_resto_id, st.session_state.popup_resto_name)
    # On efface la mémoire pour éviter que le popup ne s'ouvre en boucle
    st.session_state.popup_resto_id = None
    st.session_state.popup_resto_name = None
