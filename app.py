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
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

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
if "popup_history" not in st.session_state: st.session_state.popup_history = []
if "from_popup_nav" not in st.session_state: st.session_state.from_popup_nav = False

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

# --- RECHERCHE DRIVE INTELLIGENTE (FICHIERS HEBDOS + MASTER) ---
@st.cache_data(ttl=300)
def get_drive_files():
    results = drive_service.files().list(
        q="mimeType='text/csv' and trashed = false", 
        fields="files(id, name, parents)"
    ).execute()
    
    data_files = []
    master_file = None
    
    for f in results.get('files', []):
        if f['name'] == 'master_consolidated.csv':
            master_file = f
        elif re.search(r'data week (\d+)_(\d{4})\.csv', f['name'], re.IGNORECASE): 
            data_files.append(f)
            
    return data_files, master_file

fichiers_disponibles, master_file_info = get_drive_files()
if not fichiers_disponibles and not master_file_info:
    st.warning("⚠️ Aucun fichier trouvé sur Drive.")
    st.stop()

#==========================================
# 3. MOTEUR DE FUSION TOTALE DES FICHIERS & REFERENTIEL
# ==========================================

def clean_id_series(s):
    if s is None or len(s) == 0:
        return s
    return s.astype(str).str.strip().str.replace(r'\.0$', '', regex=True)

# --- CHARGEMENT ROBUSTE DE RST_list ---
@st.cache_data(ttl=600)
def load_rst_list_master():
    df_rst = pd.DataFrame()
    try:
        sheet_rst = gc.open("RST_list")
        records = sheet_rst.sheet1.get_all_records()
        df_rst = pd.DataFrame(records)
    except Exception:
        df_rst = pd.DataFrame()

    if df_rst.empty:
        try:
            results = drive_service.files().list(
                q="name = 'RST_list.csv' or name = 'RST_list' or name contains 'restaurant-export'",
                fields="files(id, name, mimeType)"
            ).execute()
            files = results.get('files', [])
            if files:
                req = drive_service.files().get_media(fileId=files[0]['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, req)
                done = False
                while not done: _, done = downloader.next_chunk()
                fh.seek(0)
                try:
                    df_rst = pd.read_csv(fh, sep=";", dtype=str)
                    if df_rst.shape[1] <= 2:
                        fh.seek(0); df_rst = pd.read_csv(fh, sep=",", dtype=str)
                except Exception:
                    fh.seek(0); df_rst = pd.read_csv(fh, sep=",", dtype=str)
        except Exception:
            df_rst = pd.DataFrame()

    if df_rst.empty:
        try: df_rst = pd.read_csv("restaurant-export-2026-05-15.csv", sep=";", dtype=str)
        except Exception: df_rst = pd.DataFrame()

    if not df_rst.empty:
        df_rst.columns = [str(c).strip() for c in df_rst.columns]
        col_id = next((c for c in df_rst.columns if "restaurant id" in c.lower() or c.lower() == "id"), None)
        if col_id:
            df_rst.rename(columns={col_id: 'Restaurant ID'}, inplace=True)
            df_rst['Restaurant ID'] = clean_id_series(df_rst['Restaurant ID'])
        col_name = next((c for c in df_rst.columns if "restaurant name" in c.lower()), None)
        if col_name and col_name != 'Restaurant Name':
            df_rst.rename(columns={col_name: 'Restaurant Name'}, inplace=True)
        if 'Main City' in df_rst.columns: df_rst['Main City'] = df_rst['Main City'].astype(str).str.strip()
        if 'Sub City' in df_rst.columns: df_rst['Sub City'] = df_rst['Sub City'].astype(str).str.strip()
    return df_rst

df_rst_master = load_rst_list_master()

# --- CHARGEMENT DE L'ANCIEN PÉRIMÈTRE (Old_Pipeline) ---
@st.cache_data(ttl=600)
def load_old_pipeline_master():
    df_old = pd.DataFrame()
    try:
        sheet_old = gc.open("Old_Pipeline")
        records = sheet_old.sheet1.get_all_records()
        df_old = pd.DataFrame(records)
    except Exception:
        try:
            results = drive_service.files().list(
                q="name = 'Old_Pipeline.csv' or name = 'Old_Pipeline' or name contains 'Old_Pipeline'",
                fields="files(id, name, mimeType)"
            ).execute()
            files = results.get('files', [])
            if files:
                req = drive_service.files().get_media(fileId=files[0]['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, req)
                done = False
                while not done: _, done = downloader.next_chunk()
                fh.seek(0)
                try:
                    df_old = pd.read_csv(fh, sep=";", dtype=str)
                    if df_old.shape[1] <= 1: fh.seek(0); df_old = pd.read_csv(fh, sep=",", dtype=str)
                except Exception:
                    fh.seek(0); df_old = pd.read_csv(fh, sep=",", dtype=str)
        except Exception:
            df_old = pd.DataFrame()

    if not df_old.empty:
        df_old.columns = [str(c).strip() for c in df_old.columns]
        cols = df_old.columns.tolist()
        if len(cols) >= 2:
            df_old.rename(columns={cols[0]: 'Restaurant ID', cols[1]: 'AM_Name_Old'}, inplace=True)
            df_old['Restaurant ID'] = clean_id_series(df_old['Restaurant ID'])
            df_old['AM_Name_Old'] = df_old['AM_Name_Old'].astype(str).str.strip()
    return df_old

df_old_pipeline_master = load_old_pipeline_master()

# --- FONCTION UNITAIRE DE TÉLÉCHARGEMENT ---
def download_single_csv(file_info, add_source=True):
    try:
        req = drive_service.files().get_media(fileId=file_info['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done: _, done = downloader.next_chunk()
        fh.seek(0)
        df = pd.read_csv(fh, low_memory=False)
        if not df.empty:
            if "restaurant name" in df.columns: 
                df.rename(columns={"restaurant name": "Restaurant Name"}, inplace=True)
            if add_source:
                df['source_file'] = file_info['name']
        return df
    except Exception:
        return pd.DataFrame()

# --- MOTEUR ETL INCRÉMENTAL AVEC MASTER DRIVE ---
@st.cache_data(show_spinner=False)
def load_and_consolidate_history(data_files, master_file):
    df_master = pd.DataFrame()
    fichiers_deja_merges = set()
    
    if master_file:
        df_master = download_single_csv(master_file, add_source=False)
        if not df_master.empty and 'source_file' in df_master.columns:
            fichiers_deja_merges = set(df_master['source_file'].unique())
            
    nouveaux_fichiers = [f for f in data_files if f['name'] not in fichiers_deja_merges]
    
    if len(nouveaux_fichiers) == 0 and not df_master.empty:
        return df_master
        
    nouveaux_dfs = []
    for f in nouveaux_fichiers:
        df_temp = download_single_csv(f, add_source=True)
        if not df_temp.empty: nouveaux_dfs.append(df_temp)
            
    if not nouveaux_dfs and not df_master.empty: return df_master
    elif not nouveaux_dfs and df_master.empty: return pd.DataFrame()
        
    dfs_to_concat = [df_master] + nouveaux_dfs if not df_master.empty else nouveaux_dfs
    df_final = pd.concat(dfs_to_concat, ignore_index=True)
    if 'order id' in df_final.columns:
        df_final = df_final.drop_duplicates(subset=['order id'], keep='last')
        
    try:
        csv_buffer = io.BytesIO()
        df_final.to_csv(csv_buffer, index=False, encoding='utf-8')
        csv_buffer.seek(0)
        media = MediaIoBaseUpload(csv_buffer, mimetype='text/csv', resumable=True)
        
        if master_file:
            drive_service.files().update(fileId=master_file['id'], media_body=media).execute()
        else:
            file_metadata = {'name': 'master_consolidated.csv'}
            if data_files and 'parents' in data_files[0]:
                file_metadata['parents'] = [data_files[0]['parents'][0]]
            drive_service.files().create(body=file_metadata, media_body=media).execute()
    except Exception:
        pass
        
    return df_final

try:
    with st.spinner("Vérification incrémentale de l'historique sur Drive..."):
        df_merged_full = load_and_consolidate_history(fichiers_disponibles, master_file_info)
        
        if not df_pipeline_master.empty and 'Restaurant ID' in df_pipeline_master.columns:
            df_pipeline_master['Restaurant ID'] = clean_id_series(df_pipeline_master['Restaurant ID'])

        if not df_merged_full.empty and 'Restaurant ID' in df_merged_full.columns:
            df_merged_full['Restaurant ID'] = clean_id_series(df_merged_full['Restaurant ID'])
            df_merged_full = df_merged_full[df_merged_full['Restaurant ID'] != 'nan']

        df_merged_full['order day'] = pd.to_datetime(df_merged_full['order day'])
        df_merged_full['Week'] = "Week " + df_merged_full['order day'].dt.isocalendar().week.astype(str).str.zfill(2)
        df_merged_full['Month'] = df_merged_full['order day'].dt.strftime('%Y-%m')

        cols_id_name = ['Restaurant ID', 'Restaurant Name']
        l_rst = df_rst_master[cols_id_name].dropna(subset=['Restaurant ID']) if (not df_rst_master.empty and all(c in df_rst_master.columns for c in cols_id_name)) else pd.DataFrame(columns=cols_id_name)
        l_crm = df_pipeline_master[cols_id_name].dropna(subset=['Restaurant ID']) if not df_pipeline_master.empty else pd.DataFrame(columns=cols_id_name)
        l_csv = df_merged_full[cols_id_name].dropna(subset=['Restaurant ID']) if not df_merged_full.empty else pd.DataFrame(columns=cols_id_name)

        master_restos = pd.concat([l_rst, l_crm, l_csv], ignore_index=True).drop_duplicates(subset=['Restaurant ID'], keep='first')

except Exception as e:
    st.error(f"❌ Erreur critique lors de la fusion : {e}")
    st.stop()

# --- MOTEUR DE CATÉGORISATION & EXPORT SEGMENTS FOOD ---
@st.cache_data(show_spinner=False)
def generate_food_segments_export(_df_orders, _df_rst):
    cols_id_name = ['Restaurant ID', 'Restaurant Name']
    l_rst = _df_rst[cols_id_name].dropna(subset=['Restaurant ID']) if (not _df_rst.empty and all(c in _df_rst.columns for c in cols_id_name)) else pd.DataFrame(columns=cols_id_name)
    l_ord = _df_orders[cols_id_name].dropna(subset=['Restaurant ID']) if (not _df_orders.empty and all(c in _df_orders.columns for c in cols_id_name)) else pd.DataFrame(columns=cols_id_name)
    
    df_base = pd.concat([l_rst, l_ord], ignore_index=True).drop_duplicates(subset=['Restaurant ID'], keep='first').copy()
    df_base['Restaurant ID'] = clean_id_series(df_base['Restaurant ID'])
    
    best_cat_df = pd.DataFrame(columns=['Restaurant ID', 'best seller all time category'])
    if not _df_orders.empty and 'Food Category' in _df_orders.columns:
        df_val = _df_orders.dropna(subset=['Restaurant ID', 'Food Category']).copy()
        df_val['Restaurant ID'] = clean_id_series(df_val['Restaurant ID'])
        df_val['Food Category'] = df_val['Food Category'].astype(str).str.replace(r'\[|\]|/', '', regex=True).str.strip()
        df_val = df_val[df_val['Food Category'].str.lower() != 'nan']
        
        if not df_val.empty:
            cat_counts = df_val.groupby(['Restaurant ID', 'Food Category']).size().reset_index(name='cnt')
            best_cat_df = cat_counts.sort_values(['Restaurant ID', 'cnt'], ascending=[True, False]).drop_duplicates('Restaurant ID', keep='first')
            best_cat_df.rename(columns={'Food Category': 'best seller all time category'}, inplace=True)
            
    sales_agg = pd.DataFrame(columns=['Restaurant ID', 'sales_text'])
    if not _df_orders.empty:
        df_txt = _df_orders.dropna(subset=['Restaurant ID']).copy()
        df_txt['Restaurant ID'] = clean_id_series(df_txt['Restaurant ID'])
        for c in ['Food Item', 'Food Category', 'services']:
            if c not in df_txt.columns: df_txt[c] = ''
        sales_agg = df_txt.groupby('Restaurant ID').apply(
            lambda g: ' '.join(g['Food Item'].dropna().astype(str).tolist() + g['Food Category'].dropna().astype(str).tolist() + g['services'].dropna().astype(str).tolist())
        ).reset_index(name='sales_text')

    res = pd.merge(df_base, best_cat_df[['Restaurant ID', 'best seller all time category']], on='Restaurant ID', how='left')
    res = pd.merge(res, sales_agg, on='Restaurant ID', how='left')
    
    if not _df_rst.empty and 'Cuisine Type' in _df_rst.columns:
        res = pd.merge(res, _df_rst[['Restaurant ID', 'Cuisine Type', 'Services', 'Sections']].drop_duplicates('Restaurant ID'), on='Restaurant ID', how='left')
    else:
        for c in ['Cuisine Type', 'Services', 'Sections']: res[c] = ''
        
    res['best seller all time category'] = res['best seller all time category'].fillna('N/A / Général')
    res['Type cuisine'] = res['Cuisine Type'].fillna('Général').astype(str).str.strip()
    res['sales_text'] = res['sales_text'].fillna('')

    def get_segment(row):
        txt = ' '.join([str(row['Type cuisine']), str(row['Services']), str(row['best seller all time category']), str(row['Restaurant Name']), str(row['sales_text'])]).lower()
        if any(k in txt for k in ['brunch', 'petit déj', 'petit dej', 'breakfast', 'coffee', 'café', 'cafe', 'douceur', 'sweet', 'dessert', 'glace', 'ice cream', 'gaufre', 'crêpe', 'crepe', 'pâtiss', 'patiss', 'boulang', 'bakery', 'jus', 'juice', 'smoothie', 'donut', 'churros']):
            return '🍩 Brunch & Sweet'
        if any(k in txt for k in ['pizza', 'calzone', 'pâte', 'pates', 'pasta', 'spaghet', 'penne', 'tagliatell', 'lasagn', 'macaroni', 'trattoria', 'pizzeria']):
            return '🍕 Pizza & Pasta'
        if any(k in txt for k in ['healthy', 'salad', 'salade', 'bowl', 'poke', 'diet', 'bio', 'fruit', 'légume', 'legume', 'soupe', 'soup', 'végan', 'vegan', 'fit', 'fresh', 'detox']):
            return '🥑 Fresh & Healthy'
        if any(k in txt for k in ['asiatique', 'sushi', 'wok', 'japon', 'chin', 'thai', 'ramen', 'noodle', 'nem', 'maki', 'indien', 'indian', 'liban', 'leban', 'syri', 'mexic', 'marocain', 'moroccan', 'traditionnel', 'oriental', 'turc', 'couscous', 'tajine']):
            return '🌍 World of Tastes'
        return '🍔 Street Food'

    res['Segment Food'] = res.apply(get_segment, axis=1)

    tag_kw = {
        'Tacos🌮': ['taco'], 'Burger🍔': ['burger', 'whopper', 'big mac', 'mcdo'], 'Panini 🌭': ['panini'],
        'Sandwich 🌭': ['sandwich', 'sandw', 'club', 'bocadillo', 'subway', 'baguette'], 'Pizza🍕': ['pizza', 'calzone', 'domino', 'pizz'],
        'Asiatique🍣': ['asiatique', 'sushi', 'wok', 'japon', 'chin', 'thai', 'noodle', 'ramen', 'nem', 'maki', 'roll', 'asia', 'sashimi'],
        'Shawarma🥙': ['shawarma', 'chawarma', 'chawerma', 'kebab', 'gyros', 'doner', 'syri'],
        'Poulet🍗': ['poulet', 'chicken', 'kfc', 'wings', 'nugget', 'tender', 'crispy', 'chick', 'rotiss', 'coquelet'],
        'Pâtes🍝': ['pâte', 'pates', 'pasta', 'spaghet', 'penne', 'tagliatell', 'lasagn', 'macaroni', 'bolognaise', 'carbonara']
    }
    
    for tag, kws in tag_kw.items():
        def check_tag(row, keywords=kws):
            stxt = ' '.join([str(row['sales_text']), str(row['best seller all time category'])]).lower()
            if any(k in stxt for k in keywords): return "✅ Oui"
            rtxt = ' '.join([str(row['Restaurant Name']), str(row['Type cuisine']), str(row['Services']), str(row['Sections'])]).lower()
            if any(k in rtxt for k in keywords): return "✅ Oui"
            return "❌ Non"
        res[tag] = res.apply(check_tag, axis=1)

    cols_order = ['Restaurant ID', 'Restaurant Name', 'Type cuisine', 'Segment Food', 'best seller all time category', 'Tacos🌮', 'Burger🍔', 'Panini 🌭', 'Sandwich 🌭', 'Pizza🍕', 'Asiatique🍣', 'Shawarma🥙', 'Poulet🍗', 'Pâtes🍝']
    return res[cols_order]

df_export_master = generate_food_segments_export(df_merged_full, df_rst_master)
# ==========================================
# 4. MOTEUR DE CALCULS & PROTECTION ZERO (CORRIGÉ & ROBUSTE)
# ==========================================
def compute_metrics(df_subset, group_cols):
    if df_subset.empty:
        cols = list(group_cols) + ['Requested', 'Delivered', 'Auto_Accepted', 'CancelledByRestaurant', 'GMV', 'CA', 'Commission', 'Promo_Restaurant', 'Promo_Admin', 'LR_LG_Costs']
        return pd.DataFrame(columns=cols)

    agg_dict = {
        'Requested': ('order id', 'count'),
        'Delivered': ('status', lambda x: (x == 'Delivered').sum() if 'status' in df_subset.columns else 0),
        'Auto_Accepted': ('Accepted By' if 'Accepted By' in df_subset.columns else 'order id', 
                          lambda x: x.astype(str).str.contains('restaurant', case=False, na=False).sum() if 'Accepted By' in df_subset.columns else 0),
        'CancelledByRestaurant': ('status' if 'status' in df_subset.columns else 'order id', 
                                   lambda x: x.astype(str).str.contains('restaurant', case=False, na=False).sum() if 'status' in df_subset.columns else 0),
        'GMV': ('item total' if 'item total' in df_subset.columns else 'order id', 
                lambda x: x[df_subset.loc[x.index, 'status'] == 'Delivered'].sum() if ('item total' in df_subset.columns and 'status' in df_subset.columns) else 0),
        'CA': ('admin earnings' if 'admin earnings' in df_subset.columns else 'order id', 
               lambda x: x[df_subset.loc[x.index, 'status'] == 'Delivered'].sum() if ('admin earnings' in df_subset.columns and 'status' in df_subset.columns) else 0),
        'Commission': ('restaurant commission' if 'restaurant commission' in df_subset.columns else 'order id', 
                       lambda x: x[df_subset.loc[x.index, 'status'] == 'Delivered'].sum() if ('restaurant commission' in df_subset.columns and 'status' in df_subset.columns) else 0),
        'Promo_Restaurant': ('coupon restaurant' if 'coupon restaurant' in df_subset.columns else 'order id', 
                            lambda x: x.sum() if 'coupon restaurant' in df_subset.columns else 0),
        'Promo_Admin': ('coupon admin' if 'coupon admin' in df_subset.columns else 'order id', 
                        lambda x: x.sum() if 'coupon admin' in df_subset.columns else 0),
        'LR_LG_Costs': ('driver payout' if 'driver payout' in df_subset.columns else 'order id', 
                        lambda x: x.sum() if 'driver payout' in df_subset.columns else 0)
    }

    res = df_subset.groupby(group_cols).agg(**agg_dict).reset_index()

    num_cols = ['Requested', 'Delivered', 'Auto_Accepted', 'CancelledByRestaurant', 'GMV', 'CA', 'Commission', 'Promo_Restaurant', 'Promo_Admin', 'LR_LG_Costs']
    for c in num_cols:
        if c in res.columns:
            res[c] = pd.to_numeric(res[c], errors='coerce').fillna(0)

    return res

def compare_wow(df_curr, df_prev, merge_on):
    df_comp = pd.merge(df_curr, df_prev, on=merge_on, suffixes=('', '_prev'), how='left').fillna(0)

    num_cols = [
        'Requested', 'Requested_prev', 'Delivered', 'Delivered_prev', 
        'Auto_Accepted', 'Auto_Accepted_prev', 'CancelledByRestaurant', 'CancelledByRestaurant_prev', 
        'GMV', 'GMV_prev', 'CA', 'CA_prev', 'Commission', 'Commission_prev',
        'Promo_Restaurant', 'Promo_Restaurant_prev', 'Promo_Admin', 'Promo_Admin_prev',
        'LR_LG_Costs', 'LR_LG_Costs_prev'
    ]
    for c in num_cols:
        if c in df_comp.columns:
            df_comp[c] = pd.to_numeric(df_comp[c], errors='coerce').fillna(0)

    req_curr_safe = df_comp['Requested'].replace(0, np.nan)
    req_prev_safe = df_comp['Requested_prev'].replace(0, np.nan)
    del_curr_safe = df_comp['Delivered'].replace(0, np.nan)
    del_prev_safe = df_comp['Delivered_prev'].replace(0, np.nan)
    gmv_prev_safe = df_comp['GMV_prev'].replace(0, np.nan)
    
    df_comp['Success Rate'] = (df_comp['Delivered'] / req_curr_safe).fillna(0)
    df_comp['Taux Acceptation'] = (df_comp['Auto_Accepted'] / req_curr_safe).fillna(0)
    df_comp['Taux Cancellation'] = (df_comp['CancelledByRestaurant'] / req_curr_safe).fillna(0)
    df_comp['AOV'] = (df_comp['GMV'] / del_curr_safe).fillna(0)
    
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
        if len(df_comp) >= 3: 
            df_comp['Tier'] = pd.qcut(df_comp['GMV'].rank(method='first'), q=[0, 0.4, 0.8, 1.0], labels=['Tier C', 'Tier B', 'Tier A'])
        else: 
            df_comp['Tier'] = 'Non classé'
    else: 
        df_comp['Tier'] = "N/A"
    return df_comp

# MOTEUR TEMPOREL DYNAMIQUE (ADAPTÉ AU CHOIX SEMAINE OU MOIS)
df_current = df_merged[df_merged[col_temps] == periode_selectionnee].copy()
df_prev = df_merged[df_merged[col_temps] == periode_precedente] if periode_precedente else pd.DataFrame(columns=df_merged.columns)

def get_metrics_with_zeroes(df_subset, expected_base):
    metrics = compute_metrics(df_subset, ['Restaurant ID'])
    res = pd.merge(expected_base, metrics, on='Restaurant ID', how='left').fillna(0)
    return res

# --- MAPPING VILLE / ZONE ROBUSTE (CSV + FALLBACK RST_list POUR LES RESTOS A 0 COMMANDE) ---
mapping_csv = df_merged_full[['Restaurant ID', 'Area', 'city']].dropna(subset=['Restaurant ID']).drop_duplicates('Restaurant ID')

if 'df_rst_master' in globals() and not df_rst_master.empty and 'Main City' in df_rst_master.columns and 'Sub City' in df_rst_master.columns:
    mapping_rst = df_rst_master[['Restaurant ID', 'Sub City', 'Main City']].rename(columns={'Sub City': 'Area', 'Main City': 'city'}).dropna(subset=['Restaurant ID'])
    mapping_area = pd.concat([mapping_csv, mapping_rst], ignore_index=True).drop_duplicates('Restaurant ID', keep='first')
else:
    mapping_area = mapping_csv

liste_base_overview = pd.merge(liste_attendue, mapping_area, on='Restaurant ID', how='left')
liste_base_overview['Area'] = liste_base_overview['Area'].fillna('Aucune Cmd')
liste_base_overview['city'] = liste_base_overview['city'].fillna('Inconnu')

df_current_full = get_metrics_with_zeroes(df_current, liste_base_overview)
df_prev_full = get_metrics_with_zeroes(df_prev, liste_base_overview)

# --- DÉTECTEUR DE CLIC UNIVERSEL ---
def is_new_selection(key, selection_rows):
    prev_key = f"prev_sel_{key}"
    prev = st.session_state.get(prev_key, [])
    curr = selection_rows if selection_rows else []
    st.session_state[prev_key] = curr
    return curr != prev and len(curr) > 0
    
# ==========================================
# 5. POPUP 360° UNIVERSEL (COMPATIBLE SEMAINE & MOIS + NAVIGATION RETOUR)
# ==========================================
@st.dialog("🔍 Vue 360° Détaillée", width="large")
def popup_360(entity_type, entity_id, entity_name):
    if st.session_state.get("popup_history") and len(st.session_state.popup_history) > 0:
        last_type, last_id, last_name = st.session_state.popup_history[-1]
        icon = "🏙️" if last_type == 'City' else ("🏘️" if last_type == 'Area' else ("🍕" if last_type == 'Category' else ("📅" if last_type in ['Week', 'Period', 'Month'] else "🏪")))
        
        col_bk1, col_bk2 = st.columns([2, 2])
        with col_bk1:
            if st.button(f"⬅️ Retour à : {icon} {last_name}", key=f"btn_back_{entity_id}_{len(st.session_state.popup_history)}"):
                st.session_state.popup_history.pop()
                st.session_state.from_popup_nav = True
                st.session_state.popup_entity_type = last_type
                st.session_state.popup_entity_id = last_id
                st.session_state.popup_entity_name = last_name
                st.rerun()
        st.markdown("---")

    max_global_date = df_merged_full['order day'].max()
    if pd.isna(max_global_date): 
        max_global_date = datetime.now()
    
    clean_entity_id = str(entity_id).strip().lower()

    if entity_type == 'Restaurant':
        df_r = df_merged_full[df_merged_full['Restaurant ID'].astype(str).str.strip().str.lower() == clean_entity_id].sort_values('order day')
        note_id = str(entity_id)
    elif entity_type == 'Category':
        df_r = df_merged_full[df_merged_full['Food Category'].astype(str).str.replace(r'\[|\]|/', '', regex=True).str.strip().str.lower() == clean_entity_id].sort_values('order day')
        note_id = f"Cat_{entity_id}"
    elif entity_type == 'Item':
        df_r = df_merged_full[df_merged_full['Food Item'].astype(str).str.contains(str(entity_id), regex=False, na=False)].sort_values('order day')
        note_id = f"Item_{entity_id}"
    elif entity_type in ['Week', 'Period', 'Month']:
        df_r = df_merged_full.sort_values('order day')
        note_id = f"Time_{entity_id}"
    elif entity_type == 'City':
        df_r = df_merged_full[df_merged_full['city'].astype(str).str.strip().str.lower() == clean_entity_id].sort_values('order day')
        note_id = f"City_{entity_id}"
    elif entity_type == 'Area':
        df_r = df_merged_full[df_merged_full['Area'].astype(str).str.strip().str.lower() == clean_entity_id].sort_values('order day')
        note_id = f"Area_{entity_id}"

    st.markdown(f"### {'🏪' if entity_type == 'Restaurant' else '📊'} {entity_name}")
    
    if entity_type == 'Restaurant':
        if not df_rst_master.empty:
            rst_info = df_rst_master[df_rst_master['Restaurant ID'].astype(str).str.strip().str.lower() == clean_entity_id]
            if not rst_info.empty:
                info = rst_info.iloc[0]
                c_status = str(info.get('Status', 'Inconnu'))
                c_city = str(info.get('Main City', 'N/A'))
                c_sub = str(info.get('Sub City', 'N/A'))
                c_cuisine = str(info.get('Cuisine Type', 'Général')).replace(',', ', ')
                if c_cuisine == 'nan' or not c_cuisine.strip(): c_cuisine = 'Général'
                c_comm = str(info.get('Commission %', '0'))
                c_type = str(info.get('Store Type', 'Restaurant'))
                c_phone = str(info.get('Phone', 'N/A'))
                c_email = str(info.get('Email', 'N/A'))

                badge_color = "🟢" if c_status == "Active" else ("🟠" if c_status == "Inactive" else "🔴")
                
                st.info(
                    f"### 📋 Fiche Partenaire ({c_status} {badge_color})\n"
                    f"* 🏙️ **Ville & Zone :** {c_city} - {c_sub}\n"
                    f"* 🍕 **Type de Cuisine :** {c_cuisine}\n"
                    f"* 💰 **Commission Contractuelle :** {c_comm}%\n"
                    f"* 🏪 **Format :** {c_type.capitalize()} | 📞 **Tél :** {c_phone} | ✉️ **Email :** {c_email}"
                )

    col_filtre, col_btn = st.columns([2, 1])
    if entity_type in ['Week', 'Period', 'Month']:
        with col_filtre: 
            st.info(f"Analyse figée sur : {entity_name}")
        if "Week" in str(entity_id):
            col_t_pop = 'Week'
            label_evo = "WoW"
        elif len(str(entity_id)) == 7 and "-" in str(entity_id):
            col_t_pop = 'Month'
            label_evo = "MoM"
        else:
            col_t_pop = 'Week'
            label_evo = "WoW"
            
        c_df = df_r[df_r[col_t_pop] == entity_id]
        time_list = sorted([str(t) for t in df_merged_full[col_t_pop].dropna().unique() if pd.notnull(t) and str(t) != 'nan'], reverse=True)
        try: 
            p_time = time_list[time_list.index(str(entity_id)) + 1]
        except: 
            p_time = None
        p_df = df_r[df_r[col_t_pop] == p_time] if p_time else pd.DataFrame(columns=df_r.columns)
        choix_periode = entity_name
    else:
        with col_filtre:
            choix_periode = st.radio("Filtre d'analyse :", [f"{label_evo_global} (Période Active : {periode_selectionnee})", "MoM (30 Derniers Jours)", "Historique Complet"], horizontal=True, key=f"radio_pop_{note_id}")
        
        if choix_periode.startswith("WoW") or choix_periode.startswith("MoM (Période") or "Période Active" in choix_periode:
            c_df = df_r[df_r[col_temps] == periode_selectionnee]
            p_df = df_r[df_r[col_temps] == periode_precedente] if periode_precedente else pd.DataFrame(columns=df_r.columns)
            label_evo = label_evo_global
        elif "30 Derniers Jours" in choix_periode:
            c_df = df_r[df_r['order day'] >= max_global_date - timedelta(days=30)]
            p_df = df_r[(df_r['order day'] >= max_global_date - timedelta(days=60)) & (df_r['order day'] < max_global_date - timedelta(days=30))]
            label_evo = "MoM"
        else:
            c_df = df_r
            p_df = pd.DataFrame(columns=df_r.columns)
            label_evo = "Global"

    def calc_kpis(df):
        req = len(df)
        df_deliv = df[df['status'] == 'Delivered'].copy() if 'status' in df.columns else pd.DataFrame()
        deliv = len(df_deliv)
        gmv = df_deliv['item total'].sum() if 'item total' in df_deliv.columns else 0
        aov = (gmv / deliv) if deliv > 0 else 0
        p_admin = df_deliv['coupon admin'].sum() if 'coupon admin' in df_deliv.columns else 0
        p_resto = df_deliv['coupon restaurant'].sum() if 'coupon restaurant' in df_deliv.columns else 0
        sr = (deliv / req) if req > 0 else 0
        
        t_deliv = 0
        if 'delivery time(M)' in df_deliv.columns: 
            t_deliv = df_deliv['delivery time(M)'].mean()
        elif 'delivery time' in df_deliv.columns: 
            t_deliv = df_deliv['delivery time'].mean()
            
        t_prep = 0
        if 'preparation time' in df_deliv.columns: 
            t_prep = df_deliv['preparation time'].mean()
        elif 'Ready by Restaurant' in df_deliv.columns and 'Accepted at' in df_deliv.columns:
            try:
                accepted = pd.to_datetime(df_deliv['Accepted at'].astype(str).str.replace(' /', ''), format='mixed', errors='coerce')
                ready = pd.to_datetime(df_deliv['Ready by Restaurant'].astype(str).str.replace(' /', ''), format='mixed', errors='coerce')
                t_prep = ((ready - accepted).dt.total_seconds() / 60).mean()
            except: 
                t_prep = 0
        return req, deliv, gmv, aov, p_admin, p_resto, sr, t_prep, t_deliv

    c_req, c_del, c_gmv, c_aov, c_pa, c_pr, c_sr, c_prep, c_dt = calc_kpis(c_df)
    p_req, p_del, p_gmv, p_aov, p_pa, p_pr, p_sr, p_prep, p_dt = calc_kpis(p_df)

    def format_evo(curr, prev):
        if prev == 0 and curr > 0: return "+100%"
        if prev == 0 and curr == 0: return "-"
        return f"{(curr / prev) - 1:+.1%}"

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

    st.markdown("---")

    if entity_type in ['City', 'Area', 'Category', 'Week', 'Period', 'Month']:
        st.markdown(f"#### 👥 Impact par Pipeline / AM ({entity_name})")
        
        pipe_ref = df_pipeline_master[['Restaurant ID', 'AM_Name']].drop_duplicates(subset=['Restaurant ID']) if not df_pipeline_master.empty else pd.DataFrame(columns=['Restaurant ID', 'AM_Name'])
        
        c_df_am = pd.merge(c_df, pipe_ref, on='Restaurant ID', how='left')
        c_df_am['AM_Name'] = c_df_am['AM_Name'].fillna('Non Assigné / Global')
        
        p_df_am = pd.merge(p_df, pipe_ref, on='Restaurant ID', how='left') if not p_df.empty else pd.DataFrame(columns=c_df_am.columns)
        if not p_df_am.empty and 'AM_Name' in p_df_am.columns:
            p_df_am['AM_Name'] = p_df_am['AM_Name'].fillna('Non Assigné / Global')

        def get_am_summary(df_sub):
            if df_sub.empty:
                return pd.DataFrame(columns=['AM_Name', 'Req', 'Delivered', 'Auto_Accepted', 'Delivery_Time'])
            
            dt_col = 'delivery time(M)' if 'delivery time(M)' in df_sub.columns else ('delivery time' if 'delivery time' in df_sub.columns else None)
            
            records = []
            for am, grp in df_sub.groupby('AM_Name'):
                req = len(grp)
                deliv = len(grp[grp['status'] == 'Delivered'])
                auto = grp['Accepted By'].astype(str).str.contains('restaurant', case=False, na=False).sum() if 'Accepted By' in grp.columns else 0
                
                dt = 0
                if dt_col:
                    deliv_grp = grp[grp['status'] == 'Delivered']
                    if not deliv_grp.empty:
                        dt = deliv_grp[dt_col].mean()
                
                records.append({
                    'AM_Name': am,
                    'Req': req,
                    'Delivered': deliv,
                    'Auto_Accepted': auto,
                    'Delivery_Time': dt
                })
            return pd.DataFrame(records)

        am_curr = get_am_summary(c_df_am)
        am_prev = get_am_summary(p_df_am)

        if not am_curr.empty:
            total_entity_req = am_curr['Req'].sum()
            am_merged = pd.merge(am_curr, am_prev[['AM_Name', 'Req']], on='AM_Name', suffixes=('', '_prev'), how='left').fillna({'Req_prev': 0})
            
            am_merged['Part Req'] = (am_merged['Req'] / total_entity_req).fillna(0) if total_entity_req > 0 else 0
            am_merged['Success Rate'] = (am_merged['Delivered'] / am_merged['Req']).fillna(0)
            
            req_prev_safe = am_merged['Req_prev'].replace(0, np.nan)
            am_merged['WoW Req'] = (am_merged['Req'] / req_prev_safe - 1).fillna(0)
            am_merged['Automation'] = (am_merged['Auto_Accepted'] / am_merged['Req']).fillna(0)
            
            disp_am = am_merged.sort_values('Req', ascending=False)[
                ['AM_Name', 'Req', 'Delivered', 'Part Req', 'Success Rate', 'WoW Req', 'Delivery_Time', 'Automation']
            ].copy()
            
            disp_am.columns = ['Pipeline / AM', 'Req', 'Livrées', 'Part Req (%)', 'Success Rate', f'{label_evo} Req (%)', 'Tps Liv. (min)', 'Automation (%)']
            
            st.dataframe(
                disp_am.style.format({
                    'Req': '{:,.0f}',
                    'Livrées': '{:,.0f}',
                    'Part Req (%)': '{:.1%}',
                    'Success Rate': '{:.1%}',
                    f'{label_evo} Req (%)': '{:+.1%}',
                    'Tps Liv. (min)': '{:.0f} min',
                    'Automation (%)': '{:.1%}'
                }),
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("Aucune donnée disponible pour les pipelines sur ce périmètre.")
            
        st.markdown("---")

    if entity_type in ['Week', 'Period', 'Month', 'City', 'Area', 'Category']:
        st.markdown(f"#### 📈 Tops & Flops ({entity_name}) - Volume de Commandes (🖱️ Cliquable)")
        resto_curr = compute_metrics(c_df, ['Restaurant ID', 'Restaurant Name'])
        resto_prev = compute_metrics(p_df, ['Restaurant ID', 'Restaurant Name'])
        comp_w = compare_wow(resto_curr, resto_prev, ['Restaurant ID', 'Restaurant Name'])
        
        c_t, c_f = st.columns(2)
        with c_t:
            st.success("🏆 Top 10 Accélérations")
            top10_pop = comp_w.sort_values('wow Req', ascending=False).head(10)[['Restaurant ID', 'Restaurant Name', 'wow Req', 'wow Req %']].copy()
            ev_t10 = st.dataframe(
                top10_pop.style.format({'wow Req': '{:+,.0f}', 'wow Req %': '{:+.1%}'}),
                column_config={"Restaurant ID": None},
                hide_index=True,
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row",
                key=f"pop_top10_{note_id}"
            )
            if is_new_selection(f"pop_top10_{note_id}", ev_t10.selection.rows):
                r_idx = ev_t10.selection.rows[0]
                if "popup_history" not in st.session_state: st.session_state.popup_history = []
                st.session_state.popup_history.append((entity_type, entity_id, entity_name))
                st.session_state.from_popup_nav = True
                
                st.session_state.popup_entity_type = 'Restaurant'
                st.session_state.popup_entity_id = top10_pop.iloc[r_idx]['Restaurant ID']
                st.session_state.popup_entity_name = top10_pop.iloc[r_idx]['Restaurant Name']
                st.rerun()

        with c_f:
            st.error("📉 Flop 10 Chutes")
            flop10_pop = comp_w.sort_values('wow Req', ascending=True).head(10)[['Restaurant ID', 'Restaurant Name', 'wow Req', 'wow Req %']].copy()
            ev_f10 = st.dataframe(
                flop10_pop.style.format({'wow Req': '{:+,.0f}', 'wow Req %': '{:+.1%}'}),
                column_config={"Restaurant ID": None},
                hide_index=True,
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row",
                key=f"pop_flop10_{note_id}"
            )
            if is_new_selection(f"pop_flop10_{note_id}", ev_f10.selection.rows):
                r_idx = ev_f10.selection.rows[0]
                if "popup_history" not in st.session_state: st.session_state.popup_history = []
                st.session_state.popup_history.append((entity_type, entity_id, entity_name))
                st.session_state.from_popup_nav = True
                
                st.session_state.popup_entity_type = 'Restaurant'
                st.session_state.popup_entity_id = flop10_pop.iloc[r_idx]['Restaurant ID']
                st.session_state.popup_entity_name = flop10_pop.iloc[r_idx]['Restaurant Name']
                st.rerun()

    if not c_df.empty:
        df_trend = c_df.groupby('order day').agg(Req=('order id','count'), Deliv=('status', lambda x: (x=='Delivered').sum())).reset_index()
        if not df_trend.empty:
            st.plotly_chart(px.line(df_trend, x='order day', y=['Req', 'Deliv'], title="Tendance Journalière (Période ciblée)", markers=True), use_container_width=True, key=f"chart_popup_{note_id}")
    
    st.markdown("---")
    
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
                        base_df = df_merged_full if entity_type in ['Week', 'Period', 'Month'] else df_r
                        base_df['date_only'] = base_df['order day'].dt.date
                        avant = base_df[(base_df['date_only'] < d_note) & (base_df['date_only'] >= d_note - timedelta(days=jours))]
                        apres = base_df[(base_df['date_only'] >= d_note) & (base_df['date_only'] <= d_note + timedelta(days=jours))]
                        g_av = avant[avant['status'] == 'Delivered']['item total'].sum()
                        g_ap = apres[apres['status'] == 'Delivered']['item total'].sum()
                        e_ap = (g_ap / g_av - 1) if g_av > 0 else 0
                        st.info(f"📊 Impact ({jours}j) : GMV Avant = {g_av:,.0f} MAD | GMV Après = {g_ap:,.0f} MAD ({e_ap:+.1%})")
                    except: 
                        pass
        else: 
            st.info("Aucune note pour cette entité.")

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
# 6. ONGLETS ET AFFICHAGES VISUELS (100% CLIQUABLES + BONUS PRORATA)
# ==========================================
tabs = st.tabs(["🌍 1. Macro", "📈 2. Overview", "❌ 3. Annulations", "🤖 4. Auto", "💻 5. Caisse.ma", "✨ 6. New", "👻 7. Inactifs", "🏆 8. Héros", "🍕 9. Catégories", "💰 10. Bonus", "📤 11. Export Segments"])

# ----------------------------------------
# ONGLET 1 : ANALYSE GLOBAL (MACRO)
# ----------------------------------------
with tabs[0]:
    st.markdown("#### 🌍 Analyse Macro des Performances (🖱️ Cliquez sur une période)")
    vue_temporelle = st.radio("Sélectionnez la vue globale :", ["📊 Par Semaine", "🗓️ Par Mois", "📅 Par Jour"], horizontal=True, key="macro_vue_temporelle")
    df_macro_base = df_merged.copy()
    
    if vue_temporelle == "📅 Par Jour":
        df_macro_base['Période'] = df_macro_base['order day'].dt.strftime('%Y-%m-%d')
    elif vue_temporelle == "🗓️ Par Mois":
        df_macro_base['Période'] = df_macro_base['order day'].dt.strftime('%Y-%m')
    else:
        df_macro_base['Période'] = df_macro_base['Week']

    df_macro = df_macro_base.groupby('Période').agg(
        Reçu=('order id', 'count'), Livré=('status', lambda x: (x == 'Delivered').sum()),
        GMV=('item total', lambda x: x[df_macro_base.loc[x.index, 'status'] == 'Delivered'].sum() if 'item total' in df_macro_base.columns else 0),
        CA=('admin earnings', lambda x: x[df_macro_base.loc[x.index, 'status'] == 'Delivered'].sum() if 'admin earnings' in df_macro_base.columns else 0)
    ).reset_index()

    for col in ['Reçu', 'Livré', 'GMV', 'CA']:
        df_macro[col] = pd.to_numeric(df_macro[col], errors='coerce').fillna(0)

    df_macro['AOV'] = (df_macro['GMV'] / df_macro['Livré'].replace(0, np.nan)).fillna(0)
    df_macro = df_macro.sort_values(by='Période', ascending=True)

    for col in ['Reçu', 'Livré', 'GMV', 'CA', 'AOV']: 
        df_macro[f'V. {col}'] = df_macro[col].pct_change()
        
    df_macro_display = df_macro.sort_values(by='Période', ascending=False).copy()
    for col in ['V. Reçu', 'V. Livré', 'V. GMV', 'V. CA', 'V. AOV']: 
        df_macro_display[col] = df_macro_display[col].apply(lambda x: f"{x:+.1%}" if pd.notnull(x) else "-")
    for col in ['GMV', 'CA', 'AOV']: 
        df_macro_display[col] = df_macro_display[col].apply(lambda x: f"{x:,.2f}")

    disp_macro = df_macro_display[['Période', 'Reçu', 'Livré', 'GMV', 'CA', 'AOV', 'V. Reçu', 'V. Livré', 'V. GMV', 'V. CA', 'V. AOV']]
    ev_macro = st.dataframe(disp_macro, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="macro_table_select")
    
    if is_new_selection("macro_table_select", ev_macro.selection.rows):
        idx = ev_macro.selection.rows[0]
        if "Week" in str(disp_macro.iloc[idx]['Période']):
            st.session_state.popup_entity_type = 'Week'
            st.session_state.popup_entity_id = disp_macro.iloc[idx]['Période']
            st.session_state.popup_entity_name = disp_macro.iloc[idx]['Période']

    st.markdown("---")
    df_daily = compute_metrics(df_merged, ['order day']).sort_values('order day')
    col_g1, col_g2 = st.columns(2)
    with col_g1: 
        st.plotly_chart(px.line(df_daily, x="order day", y="GMV", title="Tendance GMV", markers=True), use_container_width=True, key="macro_gmv_chart")
    with col_g2: 
        st.plotly_chart(px.line(df_daily, x="order day", y="Requested", title="Tendance Commandes Reçues", markers=True, color_discrete_sequence=['#f39c12']), use_container_width=True, key="macro_req_chart")

    st.markdown("---")
    city_curr, city_prev = compute_metrics(df_current, ['city']), compute_metrics(df_prev, ['city'])
    city_comp = compare_wow(city_curr, city_prev, ['city'])
    area_curr, area_prev = compute_metrics(df_current, ['city', 'Area']), compute_metrics(df_prev, ['city', 'Area'])
    area_comp = compare_wow(area_curr, area_prev, ['city', 'Area'])
    
    col_city, col_area = st.columns(2)
    
    with col_city:
        st.markdown("##### 🏙️ Performances par Ville (🖱️ Cliquable)")
        disp_city = city_comp[['city', 'Requested', 'wow Req %', 'GMV', 'wow GMV %', 'Success Rate']].sort_values('Requested', ascending=False)
        ev_city = st.dataframe(
            disp_city.style.format({'wow Req %': '{:+.1%}', 'GMV': '{:,.0f}', 'wow GMV %': '{:+.1%}', 'Success Rate': '{:.1%}'}), 
            hide_index=True, 
            use_container_width=True, 
            on_select="rerun", 
            selection_mode="single-row", 
            key="city_table_select"
        )
        if is_new_selection("city_table_select", ev_city.selection.rows):
            idx_c = ev_city.selection.rows[0]
            val_city = disp_city.iloc[idx_c]['city']
            st.session_state.popup_entity_type = 'City'
            st.session_state.popup_entity_id = val_city
            st.session_state.popup_entity_name = f"Ville : {val_city}"

    with col_area:
        st.markdown("##### 🏘️ Performances par Zone (🖱️ Cliquable)")
        disp_area = area_comp[['Area', 'Requested', 'wow Req %', 'GMV', 'wow GMV %', 'Success Rate']].sort_values('Requested', ascending=False).head(15)
        ev_area = st.dataframe(
            disp_area.style.format({'wow Req %': '{:+.1%}', 'GMV': '{:,.0f}', 'wow GMV %': '{:+.1%}', 'Success Rate': '{:.1%}'}), 
            hide_index=True, 
            use_container_width=True, 
            on_select="rerun", 
            selection_mode="single-row", 
            key="area_table_select"
        )
        if is_new_selection("area_table_select", ev_area.selection.rows):
            idx_a = ev_area.selection.rows[0]
            val_area = disp_area.iloc[idx_a]['Area']
            st.session_state.popup_entity_type = 'Area'
            st.session_state.popup_entity_id = val_area
            st.session_state.popup_entity_name = f"Zone : {val_area}"

# ----------------------------------------
# ONGLET 2 : OVERVIEW PIPELINE (TOUS TABLEAUX CLIQUABLES)
# ----------------------------------------
with tabs[1]:
    st.markdown("#### 📋 Base Détaillée (🖱️ Cliquez sur une ligne)")
    resto_comp = compare_wow(df_current_full, df_prev_full, ['Restaurant ID', 'Restaurant Name', 'Area'])
    
    if not df_rst_master.empty and 'Status' in df_rst_master.columns:
        resto_comp = pd.merge(
            resto_comp, 
            df_rst_master[['Restaurant ID', 'Status', 'Commission %']].drop_duplicates('Restaurant ID'),
            on='Restaurant ID', 
            how='left'
        )
        resto_comp['Status'] = resto_comp['Status'].fillna('N/A')
        resto_comp['Commission %'] = resto_comp['Commission %'].fillna('0')

    cols = ['Restaurant ID', 'Status', 'Tier', 'Area', 'Restaurant Name', 'Requested', 'Delivered', 'Success Rate', 'Taux Acceptation', 'wow T.A', 'GMV', 'wow GMV %']
    cols_exist = [c for c in cols if c in resto_comp.columns]
    df_disp = resto_comp[cols_exist].copy()
    
    for c in ['Success Rate', 'Taux Acceptation', 'wow T.A', 'wow GMV %']: 
        if c in df_disp.columns: df_disp[c] = df_disp[c].apply(lambda x: f"{x:+.1%}" if pd.notnull(x) else "-")
    for c in ['GMV']: 
        if c in df_disp.columns: df_disp[c] = df_disp[c].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) else "0")

    event = st.dataframe(df_disp, column_config={"Restaurant ID": None}, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="overview_table_select")
    if is_new_selection("overview_table_select", event.selection.rows):
        st.session_state.popup_entity_type = 'Restaurant'
        st.session_state.popup_entity_id = df_disp.iloc[event.selection.rows[0]]['Restaurant ID']
        st.session_state.popup_entity_name = df_disp.iloc[event.selection.rows[0]]['Restaurant Name']

    # --- TABLEAU ANOMALIES CLIQUABLE ---
    anomalies = resto_comp[(resto_comp['Tier'] == 'Tier A') & (resto_comp['wow delivered %'] < -0.15)]
    if not anomalies.empty:
        st.error(f"🚨 **ALERTE BUSINESS :** {len(anomalies)} restaurants du 'Tier A' ont subi une baisse de plus de 15% WoW !")
        disp_anom = anomalies[['Restaurant ID', 'Restaurant Name', 'Area', 'Requested', 'wow delivered %', 'wow GMV %']].copy()
        ev_anom = st.dataframe(
            disp_anom.style.format({'wow delivered %': '{:+.1%}', 'wow GMV %': '{:+.1%}'}),
            column_config={"Restaurant ID": None},
            hide_index=True,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            key="anomalies_table_select"
        )
        if is_new_selection("anomalies_table_select", ev_anom.selection.rows):
            r_idx = ev_anom.selection.rows[0]
            st.session_state.popup_entity_type = 'Restaurant'
            st.session_state.popup_entity_id = disp_anom.iloc[r_idx]['Restaurant ID']
            st.session_state.popup_entity_name = disp_anom.iloc[r_idx]['Restaurant Name']

    # --- TOPS & FLOPS OVERVIEW CLIQUABLES ---
    st.markdown("#### 📈 Tops & Flops (🖱️ Cliquables)")
    col_t, col_f = st.columns(2)
    with col_t: 
        st.success("🏆 **Top 30 Accélérations**")
        top30 = resto_comp.sort_values('wow delivered', ascending=False).head(30)[['Restaurant ID', 'Restaurant Name', 'Tier', 'wow delivered %']].copy()
        ev_t30 = st.dataframe(
            top30.style.format({'wow delivered %': '{:+.1%}'}),
            column_config={"Restaurant ID": None},
            hide_index=True,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            key="top30_table_select"
        )
        if is_new_selection("top30_table_select", ev_t30.selection.rows):
            r_idx = ev_t30.selection.rows[0]
            st.session_state.popup_entity_type = 'Restaurant'
            st.session_state.popup_entity_id = top30.iloc[r_idx]['Restaurant ID']
            st.session_state.popup_entity_name = top30.iloc[r_idx]['Restaurant Name']

    with col_f: 
        st.error("📉 **Flop 30 Chutes**")
        flop30 = resto_comp.sort_values('wow delivered', ascending=True).head(30)[['Restaurant ID', 'Restaurant Name', 'Tier', 'wow delivered %']].copy()
        ev_f30 = st.dataframe(
            flop30.style.format({'wow delivered %': '{:+.1%}'}),
            column_config={"Restaurant ID": None},
            hide_index=True,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            key="flop30_table_select"
        )
        if is_new_selection("flop30_table_select", ev_f30.selection.rows):
            r_idx = ev_f30.selection.rows[0]
            st.session_state.popup_entity_type = 'Restaurant'
            st.session_state.popup_entity_id = flop30.iloc[r_idx]['Restaurant ID']
            st.session_state.popup_entity_name = flop30.iloc[r_idx]['Restaurant Name']

# ----------------------------------------
# ONGLET 3 : ANNULATIONS (RÉCIDIVISTES CLIQUABLES)
# ----------------------------------------
with tabs[2]:
    st.markdown("#### ❌ Surveillance des Annulations")
    df_canc_curr = df_current[df_current['status'].str.contains('Cancelled', case=False, na=False)] if 'status' in df_current.columns else pd.DataFrame()
    
    col_c1, col_c2 = st.columns([1, 2])
    with col_c1:
        st.markdown("**Comparatif par Area**")
        if 'Area' in df_canc_curr.columns and not df_canc_curr.empty:
            canc_area = df_canc_curr.groupby('Area').size().reset_index(name='Annulations')
            m_area = pd.merge(canc_area, df_current.groupby('Area').size().reset_index(name='Total Req'), on='Area')
            
            m_area['Annulations'] = pd.to_numeric(m_area['Annulations'], errors='coerce').fillna(0)
            m_area['Total Req'] = pd.to_numeric(m_area['Total Req'], errors='coerce').fillna(0)
            
            m_area['% Cancel'] = (m_area['Annulations'] / m_area['Total Req'].replace(0, np.nan)).fillna(0)
            st.dataframe(m_area.sort_values('% Cancel', ascending=False).head(10).style.format({'% Cancel': '{:.1%}'}), hide_index=True)
            
    with col_c2:
        st.markdown("**Motifs d'Annulations**")
        if not df_canc_curr.empty and 'cancellation reason ' in df_canc_curr.columns:
            reasons = df_canc_curr['cancellation reason '].value_counts().reset_index()
            reasons.columns = ['Motif', 'Nombre']
            st.plotly_chart(px.pie(reasons, names='Motif', values='Nombre', hole=0.4), use_container_width=True, key="canc_pie_chart")

    # --- TABLEAU RÉCIDIVISTES CLIQUABLE ---
    st.markdown("#### 🚨 Les Récidivistes (🖱️ Cliquez pour analyser le resto)")
    pires = resto_comp[resto_comp['Requested'] > 5].sort_values('Taux Cancellation', ascending=False).head(15)[['Restaurant ID', 'Restaurant Name', 'Area', 'Requested', 'CancelledByRestaurant', 'Taux Cancellation', 'wow Cancellation']].copy()
    ev_pires = st.dataframe(
        pires.style.format({'Taux Cancellation': '{:.1%}', 'wow Cancellation': '{:+.1%}'}),
        column_config={"Restaurant ID": None},
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="canc_recidivistes_select"
    )
    if is_new_selection("canc_recidivistes_select", ev_pires.selection.rows):
        r_idx = ev_pires.selection.rows[0]
        st.session_state.popup_entity_type = 'Restaurant'
        st.session_state.popup_entity_id = pires.iloc[r_idx]['Restaurant ID']
        st.session_state.popup_entity_name = pires.iloc[r_idx]['Restaurant Name']

# ----------------------------------------
# ONGLET 4 : AUTOMATION (CLIQUABLE)
# ----------------------------------------
with tabs[3]:
    st.markdown("#### 🤖 Automatisation")
    if 'Accepted By' in df_current.columns:
        df_current['Is_Auto'] = df_current['Accepted By'].astype(str).str.contains('restaurant', case=False, na=False)
        auto_r = df_current.groupby('Is_Auto').agg(
            Req=('order id', 'count'), 
            Del=('status', lambda x: (x == 'Delivered').sum() if 'status' in df_current.columns else 0), 
            GMV=('item total', lambda x: x[df_current.loc[x.index, 'status'] == 'Delivered'].sum() if ('item total' in df_current.columns and 'status' in df_current.columns) else 0)
        ).reset_index()

        for col in ['Req', 'Del', 'GMV']:
            auto_r[col] = pd.to_numeric(auto_r[col], errors='coerce').fillna(0)

        auto_r['Type'] = auto_r['Is_Auto'].map({True: '🤖 Automatisé', False: '👨‍💻 Manuel'})
        req_safe = auto_r['Req'].replace(0, np.nan)
        auto_r['Success Rate'] = (auto_r['Del'] / req_safe).fillna(0)
        
        st.dataframe(auto_r[['Type', 'Req', 'Del', 'Success Rate', 'GMV']].style.format({'Success Rate': '{:.1%}', 'GMV': '{:,.0f}'}), hide_index=True)
    
    st.markdown("---")
    col_acc, col_reg = st.columns(2)
    with col_acc: 
        st.success("**🚀 Accélérations T.A (🖱️ Cliquable)**")
        auto_acc = resto_comp[resto_comp['wow T.A'] > 0].sort_values('wow T.A', ascending=False).head(10)[['Restaurant ID', 'Restaurant Name', 'Requested', 'Taux Acceptation', 'wow T.A']].copy()
        ev_auto_acc = st.dataframe(
            auto_acc.style.format({'Taux Acceptation': '{:.1%}', 'wow T.A': '{:+.1%}'}),
            column_config={"Restaurant ID": None},
            hide_index=True,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            key="auto_acc_table_select"
        )
        if is_new_selection("auto_acc_table_select", ev_auto_acc.selection.rows):
            r_idx = ev_auto_acc.selection.rows[0]
            st.session_state.popup_entity_type = 'Restaurant'
            st.session_state.popup_entity_id = auto_acc.iloc[r_idx]['Restaurant ID']
            st.session_state.popup_entity_name = auto_acc.iloc[r_idx]['Restaurant Name']

    with col_reg: 
        st.error("**⚠️ Régressions T.A (🖱️ Cliquable)**")
        auto_reg = resto_comp[resto_comp['wow T.A'] < 0].sort_values('wow T.A', ascending=True).head(10)[['Restaurant ID', 'Restaurant Name', 'Requested', 'Taux Acceptation', 'wow T.A']].copy()
        ev_auto_reg = st.dataframe(
            auto_reg.style.format({'Taux Acceptation': '{:.1%}', 'wow T.A': '{:+.1%}'}),
            column_config={"Restaurant ID": None},
            hide_index=True,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            key="auto_reg_table_select"
        )
        if is_new_selection("auto_reg_table_select", ev_auto_reg.selection.rows):
            r_idx = ev_auto_reg.selection.rows[0]
            st.session_state.popup_entity_type = 'Restaurant'
            st.session_state.popup_entity_id = auto_reg.iloc[r_idx]['Restaurant ID']
            st.session_state.popup_entity_name = auto_reg.iloc[r_idx]['Restaurant Name']

def merge_ext(df_ext, comp):
    res = pd.merge(pd.merge(df_ext[['Restaurant ID']], liste_attendue, on='Restaurant ID', how='inner'), comp.drop(columns=['Restaurant Name'], errors='ignore'), on='Restaurant ID', how='left')
    for m in ['Requested', 'Delivered', 'GMV', 'wow GMV', 'wow GMV %', 'Success Rate', 'Taux Acceptation', 'wow delivered %']:
        if m in res.columns: 
            res[m] = pd.to_numeric(res[m], errors='coerce').fillna(0)
    return res

# ----------------------------------------
# ONGLETS 5, 6, 7 : Caisse, New, Inactifs (TOUS CLIQUABLES)
# ----------------------------------------
with tabs[4]:
    st.markdown("#### 💻 Caisse.ma (🖱️ Cliquable)")
    if not df_caisse.empty:
        df_c_comp = merge_ext(df_caisse, resto_comp)
        if not df_c_comp.empty: 
            disp_caisse = df_c_comp[['Restaurant ID', 'Restaurant Name', 'Requested', 'GMV', 'wow GMV %', 'Success Rate']].copy()
            ev_c = st.dataframe(disp_caisse.style.format({'GMV': '{:,.0f}', 'wow GMV %': '{:+.1%}', 'Success Rate': '{:.1%}'}), column_config={"Restaurant ID": None}, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row", key="caisse_table_select")
            if is_new_selection("caisse_table_select", ev_c.selection.rows):
                st.session_state.popup_entity_type = 'Restaurant'
                st.session_state.popup_entity_id = disp_caisse.iloc[ev_c.selection.rows[0]]['Restaurant ID']
                st.session_state.popup_entity_name = disp_caisse.iloc[ev_c.selection.rows[0]]['Restaurant Name']

with tabs[5]:
    st.markdown("#### ✨ New Restaurants (🖱️ Cliquable)")
    if not df_new.empty:
        df_n_comp = merge_ext(df_new, resto_comp)
        if not df_n_comp.empty: 
            disp_new = df_n_comp[['Restaurant ID', 'Restaurant Name', 'Requested', 'GMV', 'Success Rate']].copy()
            ev_n = st.dataframe(disp_new.style.format({'GMV': '{:,.0f}', 'Success Rate': '{:.1%}'}), column_config={"Restaurant ID": None}, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row", key="new_table_select")
            if is_new_selection("new_table_select", ev_n.selection.rows):
                st.session_state.popup_entity_type = 'Restaurant'
                st.session_state.popup_entity_id = disp_new.iloc[ev_n.selection.rows[0]]['Restaurant ID']
                st.session_state.popup_entity_name = disp_new.iloc[ev_n.selection.rows[0]]['Restaurant Name']

with tabs[6]:
    st.markdown("#### 👻 Inactifs (🖱️ Cliquable)")
    j_inactifs = st.radio("Signaler les inactifs depuis :", [3, 7, 15, 30], format_func=lambda x: f"{x} Jours", horizontal=True, key="inactifs_jours_radio")
    max_d = df_merged['order day'].max()
    restos_actifs = df_merged[df_merged['order day'] >= max_d - timedelta(days=j_inactifs)]['Restaurant ID'].unique()
    restos_inactifs = liste_attendue[~liste_attendue['Restaurant ID'].isin(restos_actifs)][['Restaurant ID', 'Restaurant Name']].copy()
    st.error(f"⚠️ {len(restos_inactifs)} restaurants inactifs depuis {j_inactifs} jours")
    
    ev_inact = st.dataframe(
        restos_inactifs,
        column_config={"Restaurant ID": None},
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="inactifs_table_select"
    )
    if is_new_selection("inactifs_table_select", ev_inact.selection.rows):
        r_idx = ev_inact.selection.rows[0]
        st.session_state.popup_entity_type = 'Restaurant'
        st.session_state.popup_entity_id = restos_inactifs.iloc[r_idx]['Restaurant ID']
        st.session_state.popup_entity_name = restos_inactifs.iloc[r_idx]['Restaurant Name']

# ----------------------------------------
# ONGLETS 8 & 9 : Héros & Catégories (CLIQUABLES)
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
            ev_p = st.dataframe(top_items.head(15), hide_index=True, on_select="rerun", selection_mode="single-row", key="heros_table_select")
            if is_new_selection("heros_table_select", ev_p.selection.rows):
                st.session_state.popup_entity_type = 'Item'
                st.session_state.popup_entity_id = top_items.iloc[ev_p.selection.rows[0]]['Produit']
                st.session_state.popup_entity_name = top_items.iloc[ev_p.selection.rows[0]]['Produit']
        with c_p2: 
            st.plotly_chart(
                px.bar(top_items.head(10), x='Nombre', y='Produit', orientation='h', title="Top 10 Global").update_layout(yaxis={'categoryorder':'total ascending'}), 
                use_container_width=True, 
                key="hero_bar_chart"
            )
        
        st.markdown("##### 📍 Top Produits par Ville")
        if 'city' in df_items.columns:
            city_items = df_items.groupby(['city', 'Item']).size().reset_index(name='Nombre').sort_values(['city', 'Nombre'], ascending=[True, False])
            st.dataframe(city_items.groupby('city').head(5).reset_index(drop=True), hide_index=True)

with tabs[8]:
    st.markdown("#### 🍕 Catégories Food (🖱️ Cliquable)")
    if 'Food Category' in df_current.columns:
        df_current_cat = df_current[df_current['Food Category'].astype(str) != 'nan'].copy()
        df_current_cat['Food Category'] = df_current_cat['Food Category'].astype(str).str.replace(r'\[|\]|/', '', regex=True).str.strip()
        df_cat = compute_metrics(df_current_cat, ['Food Category'])
        
        for col in ['Requested', 'Delivered', 'GMV']:
            if col in df_cat.columns:
                df_cat[col] = pd.to_numeric(df_cat[col], errors='coerce').fillna(0)

        df_cat['Success Rate'] = (df_cat['Delivered'] / df_cat['Requested'].replace(0, np.nan)).fillna(0)
        df_cat['AOV'] = (df_cat['GMV'] / df_cat['Delivered'].replace(0, np.nan)).fillna(0)
        
        df_cat_disp = df_cat.sort_values('Requested', ascending=False)
        disp_cat = df_cat_disp[['Food Category', 'Requested', 'Delivered', 'Success Rate', 'GMV', 'AOV']].copy()
        
        c_c1, c_c2 = st.columns(2)
        with c_c1: 
            st.plotly_chart(
                px.pie(df_cat_disp.head(10), names='Food Category', values='Requested', hole=0.4), 
                use_container_width=True, 
                key="cat_pie_chart"
            )
        with c_c2: 
            st.plotly_chart(
                px.bar(df_cat_disp.sort_values('GMV', ascending=False).head(10), x='Food Category', y='GMV'), 
                use_container_width=True, 
                key="cat_bar_chart"
            )
        
        ev_cat = st.dataframe(
            disp_cat.style.format({'Success Rate': '{:.1%}', 'GMV': '{:,.0f}', 'AOV': '{:,.0f}'}), 
            hide_index=True, 
            use_container_width=True, 
            on_select="rerun", 
            selection_mode="single-row",
            key="cat_table_select"
        )
        if is_new_selection("cat_table_select", ev_cat.selection.rows):
            st.session_state.popup_entity_type = 'Category'
            st.session_state.popup_entity_id = disp_cat.iloc[ev_cat.selection.rows[0]]['Food Category']
            st.session_state.popup_entity_name = disp_cat.iloc[ev_cat.selection.rows[0]]['Food Category']

# ----------------------------------------
# ONGLET 10 : BONUS & PRIMES (RÉSERVÉ NAJWA / ADMIN - AVEC SIMULATEUR OLD_PIPELINE SÉCURISÉ)
# ----------------------------------------
with tabs[9]:
    st.markdown("#### 💰 Calculateur de Primes Trimestrielles (Quarter over Quarter)")
    
    utilisateur_actuel = st.session_state.get("user", "").lower()
    if utilisateur_actuel not in ['najwa', 'admin']:
        st.error("🔒 **Accès Restreint :** Cet onglet est confidentiel et exclusivement réservé à l'administration et à Najwa.")
    else:
        st.success(f"🔓 **Accès Direction Autorisé** — Analyse des primes active pour le périmètre : **{am_choisi}**")
        st.info("ℹ️ **Règle de Prime :** Prorata à partir de **80% d'atteinte** de l'objectif (Plafond à 100% = 2 000 DH par KPI / Max 6 000 DH au total).")
        
        df_q_base = df_merged.copy()
        df_q_base['Quarter'] = df_q_base['order day'].dt.year.astype(str) + "-Q" + df_q_base['order day'].dt.quarter.astype(str)
        
        q_metrics = compute_metrics(df_q_base, ['Quarter']).sort_values('Quarter', ascending=True)
        
        if not q_metrics.empty:
            q_metrics['GMV_prev'] = q_metrics['GMV'].shift(1)
            q_metrics['Growth GMV'] = (q_metrics['GMV'] / q_metrics['GMV_prev'].replace(0, np.nan) - 1).fillna(0)
            q_metrics['Taux Cancel'] = (q_metrics['CancelledByRestaurant'] / q_metrics['Requested'].replace(0, np.nan)).fillna(0)
            q_metrics['Taux Auto'] = (q_metrics['Auto_Accepted'] / q_metrics['Requested'].replace(0, np.nan)).fillna(0)
            
            # 1. CALCUL DU TAUX D'ATTEINTE (PLAFONNÉ À 100% / 1.0 MAX)
            q_metrics['Atteinte GMV'] = np.where(q_metrics['GMV_prev'] > 0, np.clip(q_metrics['Growth GMV'] / 0.30, 0, 1.0), 0)
            q_metrics['Atteinte Cancel'] = np.where(q_metrics['Taux Cancel'] > 0, np.clip(0.03 / q_metrics['Taux Cancel'], 0, 1.0), 1.0)
            q_metrics['Atteinte Cancel'] = np.where(q_metrics['Requested'] > 0, q_metrics['Atteinte Cancel'], 0)
            q_metrics['Atteinte Auto'] = np.where(q_metrics['Requested'] > 0, np.clip(q_metrics['Taux Auto'] / 0.50, 0, 1.0), 0)
            
            # 2. CALCUL DES PRIMES : SI ATTEINTE >= 80% -> ATTEINTE * 2000 DH, SINON 0 DH
            q_metrics['Prime GMV (DH)'] = np.where(q_metrics['Atteinte GMV'] >= 0.80, q_metrics['Atteinte GMV'] * 2000, 0)
            q_metrics['Prime Cancel (DH)'] = np.where(q_metrics['Atteinte Cancel'] >= 0.80, q_metrics['Atteinte Cancel'] * 2000, 0)
            q_metrics['Prime Auto (DH)'] = np.where(q_metrics['Atteinte Auto'] >= 0.80, q_metrics['Atteinte Auto'] * 2000, 0)
            
            q_metrics['Total Prime (DH)'] = q_metrics['Prime GMV (DH)'] + q_metrics['Prime Cancel (DH)'] + q_metrics['Prime Auto (DH)']
            
            last_row = q_metrics.iloc[-1]
            st.markdown(f"##### 🎯 Performance Trimestre Actif (**{last_row['Quarter']}**) vs Objectifs")
            b_q1, b_q2, b_q3 = st.columns(3)
            with b_q1:
                stat_badge = "🟢" if last_row['Atteinte GMV'] == 1.0 else ("🟡" if last_row['Atteinte GMV'] >= 0.80 else "🔴")
                st.markdown(f"<div class='purple-box'><h3>Croissance GMV (Obj: ≥30%)</h3><h2>{last_row['Growth GMV']:+.1%}</h2><p>{stat_badge} Atteinte: {last_row['Atteinte GMV']:.1%} ➡️ <b>{last_row['Prime GMV (DH)']:,.0f} DH</b></p></div>", unsafe_allow_html=True)
            with b_q2:
                stat_badge = "🟢" if last_row['Atteinte Cancel'] == 1.0 else ("🟡" if last_row['Atteinte Cancel'] >= 0.80 else "🔴")
                st.markdown(f"<div class='purple-box'><h3>Annulations Resto (Obj: ≤3%)</h3><h2>{last_row['Taux Cancel']:.1%}</h2><p>{stat_badge} Atteinte: {last_row['Atteinte Cancel']:.1%} ➡️ <b>{last_row['Prime Cancel (DH)']:,.0f} DH</b></p></div>", unsafe_allow_html=True)
            with b_q3:
                stat_badge = "🟢" if last_row['Atteinte Auto'] == 1.0 else ("🟡" if last_row['Atteinte Auto'] >= 0.80 else "🔴")
                st.markdown(f"<div class='purple-box'><h3>Taux Automation (Obj: ≥50%)</h3><h2>{last_row['Taux Auto']:.1%}</h2><p>{stat_badge} Atteinte: {last_row['Atteinte Auto']:.1%} ➡️ <b>{last_row['Prime Auto (DH)']:,.0f} DH</b></p></div>", unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown("##### 📋 Historique et Primes Trimestrielles (Périmètre sélectionné)")
            
            disp_q = q_metrics.sort_values('Quarter', ascending=False).copy()
            
            def format_kpi_prime(val_pct, att_pct, prime_dh, is_growth=False, is_cancel=False):
                icon = "🟢" if att_pct == 1.0 else ("🟡" if att_pct >= 0.80 else "🔴")
                val_str = f"{val_pct:+.1%}" if is_growth else f"{val_pct:.1%}"
                return f"{icon} {val_str} (Att: {att_pct:.0%} ➡️ {prime_dh:,.0f} DH)"

            disp_q['Croissance GMV (≥30%)'] = disp_q.apply(lambda r: format_kpi_prime(r['Growth GMV'], r['Atteinte GMV'], r['Prime GMV (DH)'], is_growth=True), axis=1)
            disp_q['Annulations Resto (≤3%)'] = disp_q.apply(lambda r: format_kpi_prime(r['Taux Cancel'], r['Atteinte Cancel'], r['Prime Cancel (DH)'], is_cancel=True), axis=1)
            disp_q['Automation (≥50%)'] = disp_q.apply(lambda r: format_kpi_prime(r['Taux Auto'], r['Atteinte Auto'], r['Prime Auto (DH)']), axis=1)
            
            table_bonus = disp_q[[
                'Quarter', 'Requested', 'GMV', 
                'Croissance GMV (≥30%)', 'Annulations Resto (≤3%)', 'Automation (≥50%)', 
                'Total Prime (DH)'
            ]]
            
            st.dataframe(
                table_bonus.style.format({
                    'Requested': '{:,.0f}',
                    'GMV': '{:,.0f} MAD',
                    'Total Prime (DH)': '💰 {:,.0f} DH'
                }),
                hide_index=True,
                use_container_width=True
            )
            
            # --- VUE MANAGEMENT : COMPARATIF PAR AM ---
            st.markdown("---")
            st.markdown("##### 🏆 Vue Direction : Comparatif des Account Managers (Dernier Trimestre)")
            
            df_all_q = df_merged_full.copy()
            df_all_q['Quarter'] = df_all_q['order day'].dt.year.astype(str) + "-Q" + df_all_q['order day'].dt.quarter.astype(str)
            
            pipe_ref = df_pipeline_master[['Restaurant ID', 'AM_Name']].drop_duplicates(subset=['Restaurant ID']) if not df_pipeline_master.empty else pd.DataFrame(columns=['Restaurant ID', 'AM_Name'])
            df_all_q = pd.merge(df_all_q.drop(columns=['AM_Name'], errors='ignore'), pipe_ref, on='Restaurant ID', how='left')
            df_all_q['AM_Name'] = df_all_q['AM_Name'].fillna('Non Assigné / Global')
                
            ams_metrics = compute_metrics(df_all_q, ['AM_Name', 'Quarter']).sort_values(['AM_Name', 'Quarter'])
            ams_metrics['GMV_prev'] = ams_metrics.groupby('AM_Name')['GMV'].shift(1)
            ams_metrics['Growth GMV'] = (ams_metrics['GMV'] / ams_metrics['GMV_prev'].replace(0, np.nan) - 1).fillna(0)
            ams_metrics['Taux Cancel'] = (ams_metrics['CancelledByRestaurant'] / ams_metrics['Requested'].replace(0, np.nan)).fillna(0)
            ams_metrics['Taux Auto'] = (ams_metrics['Auto_Accepted'] / ams_metrics['Requested'].replace(0, np.nan)).fillna(0)
            
            ams_metrics['Att GMV'] = np.where(ams_metrics['GMV_prev'] > 0, np.clip(ams_metrics['Growth GMV'] / 0.30, 0, 1.0), 0)
            ams_metrics['Att Cancel'] = np.where(ams_metrics['Taux Cancel'] > 0, np.clip(0.03 / ams_metrics['Taux Cancel'], 0, 1.0), 1.0)
            ams_metrics['Att Cancel'] = np.where(ams_metrics['Requested'] > 0, ams_metrics['Att Cancel'], 0)
            ams_metrics['Att Auto'] = np.where(ams_metrics['Requested'] > 0, np.clip(ams_metrics['Taux Auto'] / 0.50, 0, 1.0), 0)
            
            ams_metrics['Prime GMV'] = np.where(ams_metrics['Att GMV'] >= 0.80, ams_metrics['Att GMV'] * 2000, 0)
            ams_metrics['Prime Cancel'] = np.where(ams_metrics['Att Cancel'] >= 0.80, ams_metrics['Att Cancel'] * 2000, 0)
            ams_metrics['Prime Auto'] = np.where(ams_metrics['Att Auto'] >= 0.80, ams_metrics['Att Auto'] * 2000, 0)
            ams_metrics['Total Prime'] = ams_metrics['Prime GMV'] + ams_metrics['Prime Cancel'] + ams_metrics['Prime Auto']
            
            dernier_trimestre = ams_metrics['Quarter'].max()
            if pd.notnull(dernier_trimestre):
                ams_last = ams_metrics[ams_metrics['Quarter'] == dernier_trimestre].copy()
                ams_last = ams_last[ams_last['AM_Name'] != 'Non Assigné / Global']
                
                ams_last['Croissance GMV'] = ams_last.apply(lambda r: f"{r['Growth GMV']:+.1%} (Att: {r['Att GMV']:.0%} ➡️ {r['Prime GMV']:,.0f} DH)", axis=1)
                ams_last['Annulations Resto'] = ams_last.apply(lambda r: f"{r['Taux Cancel']:.1%} (Att: {r['Att Cancel']:.0%} ➡️ {r['Prime Cancel']:,.0f} DH)", axis=1)
                ams_last['Automation'] = ams_last.apply(lambda r: f"{r['Taux Auto']:.1%} (Att: {r['Att Auto']:.0%} ➡️ {r['Prime Auto']:,.0f} DH)", axis=1)
                
                table_am = ams_last[['AM_Name', 'Requested', 'GMV', 'Croissance GMV', 'Annulations Resto', 'Automation', 'Total Prime']].sort_values('Total Prime', ascending=False)
                table_am.columns = ['Account Manager', 'Commandes', 'GMV (MAD)', 'Croissance GMV (≥30%)', 'Cancel Resto (≤3%)', 'Automation (≥50%)', 'Prime Gagnée (DH)']
                
                st.dataframe(
                    table_am.style.format({
                        'Commandes': '{:,.0f}',
                        'GMV (MAD)': '{:,.0f} MAD',
                        'Prime Gagnée (DH)': '💰 {:,.0f} DH'
                    }),
                    hide_index=True,
                    use_container_width=True
                )
        else:
            st.info("Aucune donnée disponible pour le calcul des primes.")

        # --- 3. SIMULATEUR PROVISOIRE Q2 (CONNECTÉ À OLD_PIPELINE & 100% SÉCURISÉ CONTRE LES VALEURS NULLES) ---
        st.markdown("---")
        st.markdown("#### 🛠️ Simulateur Provisoire Q2 (Ancien Périmètre : Google Sheet `Old_Pipeline`)")
        
        if 'df_old_pipeline_master' in globals() and not df_old_pipeline_master.empty:
            st.success(f"✅ **Fichier `Old_Pipeline` connecté** — {len(df_old_pipeline_master):,} restaurants répertoriés dans l'ancienne organisation.")
        else:
            st.warning("⚠️ Fichier `Old_Pipeline` non accessible ou vide. Mode secours par ville activé.")
        
        col_sim_conf, col_sim_res = st.columns([1, 2])
        with col_sim_conf:
            st.markdown("##### ⚙️ Configuration AM (Q2)")
            
            ams_dispos = ["Houda", "Chaima", "Najwa", "Imane", "Custom"]
            if 'df_old_pipeline_master' in globals() and not df_old_pipeline_master.empty and 'AM_Name_Old' in df_old_pipeline_master.columns:
                ams_from_sheet = sorted([str(a).strip() for a in df_old_pipeline_master['AM_Name_Old'].dropna().unique() if pd.notnull(a) and str(a).strip() not in ['nan', '', 'None', '<NA>']])
                if ams_from_sheet:
                    ams_dispos = ams_from_sheet + [a for a in ams_dispos if a not in ams_from_sheet]
            
            sim_am = st.selectbox("👤 Sélectionner l'AM :", ams_dispos, key="sim_q2_am")
            
            # RECHERCHE DIRECTE DES RESTAURANTS DE L'AM DANS OLD_PIPELINE
            ids_old_am = []
            if 'df_old_pipeline_master' in globals() and not df_old_pipeline_master.empty and 'AM_Name_Old' in df_old_pipeline_master.columns:
                ids_old_am = df_old_pipeline_master[df_old_pipeline_master['AM_Name_Old'].astype(str).str.lower() == sim_am.lower()]['Restaurant ID'].unique().tolist()
            
            if ids_old_am:
                st.info(f"📌 **{len(ids_old_am)}** restaurants automatiquement attribués à **{sim_am}** via `Old_Pipeline`.")
                restos_associes = df_merged_full[df_merged_full['Restaurant ID'].isin(ids_old_am)]
                
                # --- SÉCURISATION BLINDÉE CONTRE LES NOMS VIDES ---
                list_noms = sorted([str(r).strip() for r in restos_associes['Restaurant Name'].dropna().unique() if pd.notnull(r) and str(r).strip() not in ['nan', '', 'None', '<NA>']])
                default_kam = [r for r in list_noms if any(k in r.lower() for k in ['mcdo', 'kfc', 'burger king', 'pizza hut', 'domino', 'starbucks', 'carrefour', 'paul', 'baskin'])]
                sim_excl_kam = st.multiselect("🏢 Exclure des chaînes / KAM (optionnel) :", list_noms, default=default_kam, key="sim_q2_kam_old")
                
                df_prov = df_merged_full[
                    (df_merged_full['Restaurant ID'].isin(ids_old_am)) & 
                    (~df_merged_full['Restaurant Name'].astype(str).isin(sim_excl_kam))
                ].copy()
            else:
                # Mode secours par villes si l'AM n'est pas trouvé dans Old_Pipeline
                all_cities = sorted([str(c).strip() for c in df_merged_full['city'].dropna().unique() if pd.notnull(c) and str(c).strip() not in ['nan', '', 'None', '<NA>']])
                presets_am = {"Houda": ["Casablanca", "Mohammedia"], "Chaima": ["Rabat", "Salé", "Kenitra"], "Najwa": ["Marrakech", "Agadir", "Tanger"], "Imane": ["Fès", "Meknès", "Oujda"]}
                def_cities = [c for c in presets_am.get(sim_am, all_cities[:2]) if c in all_cities]
                sim_cities = st.multiselect("🏙️ Villes assignées (secours) :", all_cities, default=def_cities if def_cities else all_cities, key="sim_q2_cities")
                
                # --- SÉCURISATION BLINDÉE DU TRI DES RESTAURANTS PAR VILLE ---
                restos_in_cities = sorted([str(r).strip() for r in df_merged_full[df_merged_full['city'].isin(sim_cities)]['Restaurant Name'].dropna().unique() if pd.notnull(r) and str(r).strip() not in ['nan', '', 'None', '<NA>']])
                default_kam = [r for r in restos_in_cities if any(k in r.lower() for k in ['mcdo', 'kfc', 'burger king', 'pizza hut', 'domino', 'starbucks', 'carrefour', 'paul', 'baskin'])]
                sim_excl_kam = st.multiselect("🏢 Chaînes / KAM à exclure :", restos_in_cities, default=default_kam, key="sim_q2_kam_old_fb")
                
                df_prov = df_merged_full[(df_merged_full['city'].isin(sim_cities)) & (~df_merged_full['Restaurant Name'].astype(str).isin(sim_excl_kam))].copy()

            all_quarters = sorted([str(q).strip() for q in (df_merged_full['order day'].dt.year.astype(str) + "-Q" + df_merged_full['order day'].dt.quarter.astype(str)).dropna().unique() if pd.notnull(q) and str(q).strip() not in ['nan', '', 'None', '<NA>']], reverse=True)
            def_q2 = next((q for q in all_quarters if "Q2" in q), all_quarters[0] if all_quarters else "2026-Q2")
            sim_target_q = st.selectbox("🎯 Trimestre cible :", all_quarters, index=all_quarters.index(def_q2) if def_q2 in all_quarters else 0, key="sim_q2_target")

        with col_sim_res:
            st.markdown(f"##### 📊 Résultats Simulés pour **{sim_am}** ({sim_target_q})")
            
            if df_prov.empty:
                st.warning("⚠️ Aucune donnée trouvée pour cet AM dans `Old_Pipeline`. Vérifiez que l'AM existe bien dans la colonne B.")
            else:
                df_prov['Quarter'] = df_prov['order day'].dt.year.astype(str) + "-Q" + df_prov['order day'].dt.quarter.astype(str)
                q_prov = compute_metrics(df_prov, ['Quarter']).sort_values('Quarter', ascending=True)
                
                if not q_prov.empty:
                    q_prov['GMV_prev'] = q_prov['GMV'].shift(1)
                    q_prov['Growth GMV'] = (q_prov['GMV'] / q_prov['GMV_prev'].replace(0, np.nan) - 1).fillna(0)
                    q_prov['Taux Cancel'] = (q_prov['CancelledByRestaurant'] / q_prov['Requested'].replace(0, np.nan)).fillna(0)
                    q_prov['Taux Auto'] = (q_prov['Auto_Accepted'] / q_prov['Requested'].replace(0, np.nan)).fillna(0)
                    
                    q_prov['Att GMV'] = np.where(q_prov['GMV_prev'] > 0, np.clip(q_prov['Growth GMV'] / 0.30, 0, 1.0), 0)
                    q_prov['Att Cancel'] = np.where(q_prov['Taux Cancel'] > 0, np.clip(0.03 / q_prov['Taux Cancel'], 0, 1.0), 1.0)
                    q_prov['Att Cancel'] = np.where(q_prov['Requested'] > 0, q_prov['Att Cancel'], 0)
                    q_prov['Att Auto'] = np.where(q_prov['Requested'] > 0, np.clip(q_prov['Taux Auto'] / 0.50, 0, 1.0), 0)
                    
                    q_prov['Prime GMV (DH)'] = np.where(q_prov['Att GMV'] >= 0.80, q_prov['Att GMV'] * 2000, 0)
                    q_prov['Prime Cancel (DH)'] = np.where(q_prov['Att Cancel'] >= 0.80, q_prov['Att Cancel'] * 2000, 0)
                    q_prov['Prime Auto (DH)'] = np.where(q_prov['Att Auto'] >= 0.80, q_prov['Att Auto'] * 2000, 0)
                    q_prov['Total Prime (DH)'] = q_prov['Prime GMV (DH)'] + q_prov['Prime Cancel (DH)'] + q_prov['Prime Auto (DH)']
                    
                    if sim_target_q in q_prov['Quarter'].values:
                        row_prov = q_prov[q_prov['Quarter'] == sim_target_q].iloc[0]
                        
                        p_q1, p_q2, p_q3 = st.columns(3)
                        with p_q1:
                            badge = "🟢" if row_prov['Att GMV'] == 1.0 else ("🟡" if row_prov['Att GMV'] >= 0.80 else "🔴")
                            st.markdown(f"<div class='purple-box'><h3>Croissance GMV (≥30%)</h3><h2>{row_prov['Growth GMV']:+.1%}</h2><p>{badge} Att: {row_prov['Att GMV']:.0%} ➡️ <b>{row_prov['Prime GMV (DH)']:,.0f} DH</b></p></div>", unsafe_allow_html=True)
                        with p_q2:
                            badge = "🟢" if row_prov['Att Cancel'] == 1.0 else ("🟡" if row_prov['Att Cancel'] >= 0.80 else "🔴")
                            st.markdown(f"<div class='purple-box'><h3>Cancel Resto (≤3%)</h3><h2>{row_prov['Taux Cancel']:.1%}</h2><p>{badge} Att: {row_prov['Att Cancel']:.0%} ➡️ <b>{row_prov['Prime Cancel (DH)']:,.0f} DH</b></p></div>", unsafe_allow_html=True)
                        with p_q3:
                            badge = "🟢" if row_prov['Att Auto'] == 1.0 else ("🟡" if row_prov['Att Auto'] >= 0.80 else "🔴")
                            st.markdown(f"<div class='purple-box'><h3>Automation (≥50%)</h3><h2>{row_prov['Taux Auto']:.1%}</h2><p>{badge} Att: {row_prov['Att Auto']:.0%} ➡️ <b>{row_prov['Prime Auto (DH)']:,.0f} DH</b></p></div>", unsafe_allow_html=True)
                        
                        st.success(f"💰 **Prime Totale Simulée ({sim_am} - {sim_target_q}) : {row_prov['Total Prime (DH)']:,.0f} DH** sur un plafond de 6 000 DH.")
                    else:
                        st.info(f"Le trimestre {sim_target_q} n'a pas encore de données dans cette configuration.")
                        
                    disp_sim = q_prov.sort_values('Quarter', ascending=False).copy()
                    disp_sim['Croissance GMV'] = disp_sim.apply(lambda r: f"{r['Growth GMV']:+.1%} (Att: {r['Att GMV']:.0%} ➡️ {r['Prime GMV (DH)']:,.0f} DH)", axis=1)
                    disp_sim['Annulations Resto'] = disp_sim.apply(lambda r: f"{r['Taux Cancel']:.1%} (Att: {r['Att Cancel']:.0%} ➡️ {r['Prime Cancel (DH)']:,.0f} DH)", axis=1)
                    disp_sim['Automation'] = disp_sim.apply(lambda r: f"{r['Taux Auto']:.1%} (Att: {r['Att Auto']:.0%} ➡️ {r['Prime Auto (DH)']:,.0f} DH)", axis=1)
                    
                    st.dataframe(
                        disp_sim[['Quarter', 'Requested', 'GMV', 'Croissance GMV', 'Annulations Resto', 'Automation', 'Total Prime (DH)']].style.format({
                            'Requested': '{:,.0f}',
                            'GMV': '{:,.0f} MAD',
                            'Total Prime (DH)': '💰 {:,.0f} DH'
                        }),
                        hide_index=True,
                        use_container_width=True
                    )
                else:
                    st.info("Aucune commande trouvée pour ce périmètre.")

# ----------------------------------------
# ONGLET 11 : EXPORT SEGMENTS FOOD & TAGS (100% CLIQUABLE)
# ----------------------------------------
with tabs[10]:
    st.markdown("#### 📤 Export & Classification des Restaurants par Segment Food et Spécialités")
    st.info("ℹ️ **Méthodologie :** La classification détecte en priorité les spécialités vendues dans l'historique (`Food Item` & `Food Category`). Si le produit n'apparaît pas dans les transactions récentes, le moteur se base sur le `Restaurant Name` et le référentiel `RST_list`.")
    
    col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
    with col_f1:
        seg_filter = st.multiselect("🏷️ Filtrer par Segment Food :", ["🌍 World of Tastes", "🍔 Street Food", "🍩 Brunch & Sweet", "🍕 Pizza & Pasta", "🥑 Fresh & Healthy"], default=[], key="exp_seg_sel")
    with col_f2:
        tag_filter = st.selectbox("🌮 Filtrer par Spécialité / Tag :", ["Tous les restaurants", "Tacos🌮", "Burger🍔", "Panini 🌭", "Sandwich 🌭", "Pizza🍕", "Asiatique🍣", "Shawarma🥙", "Poulet🍗", "Pâtes🍝"], key="exp_tag_sel")
    with col_f3:
        search_name = st.text_input("🔍 Rechercher par Nom de Restaurant :", "", key="exp_name_srch")
        
    df_exp_disp = df_export_master.copy()
    
    if seg_filter:
        df_exp_disp = df_exp_disp[df_exp_disp['Segment Food'].isin(seg_filter)]
    if tag_filter != "Tous les restaurants":
        df_exp_disp = df_exp_disp[df_exp_disp[tag_filter] == "✅ Oui"]
    if search_name.strip():
        df_exp_disp = df_exp_disp[df_exp_disp['Restaurant Name'].astype(str).str.contains(search_name.strip(), case=False, na=False)]
        
    st.markdown(f"##### 📋 Liste des Restaurants classés (**{len(df_exp_disp):,}** résultats)")
    
    # Boutons d'export direct en CSV
    col_d1, col_d2 = st.columns([1, 4])
    with col_d1:
        csv_data = df_exp_disp.to_csv(index=False, sep=";", encoding='utf-8-sig')
        st.download_button("📥 Télécharger (CSV Excel)", data=csv_data, file_name=f"Yassir_Export_Segments_Tags_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv", use_container_width=True)
        
    # Tableau 100% Cliquable vers la vue 360°
    ev_export = st.dataframe(
        df_exp_disp,
        column_config={"Restaurant ID": None},
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="export_table_select"
    )
    if is_new_selection("export_table_select", ev_export.selection.rows):
        r_idx = ev_export.selection.rows[0]
        st.session_state.popup_entity_type = 'Restaurant'
        st.session_state.popup_entity_id = df_exp_disp.iloc[r_idx]['Restaurant ID']
        st.session_state.popup_entity_name = df_exp_disp.iloc[r_idx]['Restaurant Name']

# ==========================================
# GESTION SÉCURISÉE DU POPUP (FIN DU FICHIER)
# ==========================================
if st.session_state.get("popup_entity_id") is not None and st.session_state.get("popup_entity_type") is not None:
    if not st.session_state.get("from_popup_nav", False):
        st.session_state.popup_history = []
    st.session_state.from_popup_nav = False

    popup_360(st.session_state.popup_entity_type, st.session_state.popup_entity_id, st.session_state.popup_entity_name)
    st.session_state.popup_entity_id = None
    st.session_state.popup_entity_type = None
    st.session_state.popup_entity_name = None
