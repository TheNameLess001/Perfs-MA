import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import timedelta

# ==========================================
# 1. CONFIGURATION DE LA PAGE
# ==========================================
st.set_page_config(page_title="Yassir Control Tower", page_icon="🍔", layout="wide")

st.title("📊 Control Tower Yassir")
st.markdown("---")

# ==========================================
# 2. EN-TÊTE ET CONTRÔLES
# ==========================================
st.markdown("### ⚙️ Configuration & Données")
vue_globale = st.radio("Portée de l'analyse :", ["🇲🇦 Global Maroc", "🎯 Par Account Manager (Pipeline)"], horizontal=True)

col_am, col_upload = st.columns([1, 2])
with col_am:
    if vue_globale == "🎯 Par Account Manager (Pipeline)":
        am_choisi = st.selectbox("Pipeline", ["Houda", "Yassine", "Sara", "Amine"], label_visibility="collapsed")
    else:
        am_choisi = "Global"

with col_upload:
    fichier_data = st.file_uploader("Upload Data (admin-earnings...csv)", type=["csv", "xlsx"], label_visibility="collapsed")

st.markdown("---")
if fichier_data is None:
    st.info("👋 Veuillez uploader le fichier Data de la semaine pour générer la Control Tower.")
    st.stop()

# ==========================================
# 3. MOTEUR DE DONNÉES
# ==========================================
try:
    df_data = pd.read_csv(fichier_data)
    if "restaurant name" in df_data.columns and "Restaurant Name" not in df_data.columns:
        df_data.rename(columns={"restaurant name": "Restaurant Name"}, inplace=True)

    # Chargement dynamique des listes
    if vue_globale == "🎯 Par Account Manager (Pipeline)":
        df_pipeline = pd.read_csv(f"Pipeline - {am_choisi}.csv", sep=None, engine='python')
        df_merged = pd.merge(df_data, df_pipeline, on="Restaurant ID", how="inner")
        liste_attendue = df_pipeline[['Restaurant ID', 'Restaurant Name']].drop_duplicates()
    else:
        df_merged = df_data.copy()
        df_merged['Segment'] = 'Global'
        liste_attendue = df_merged[['Restaurant ID', 'Restaurant Name']].drop_duplicates()

    # Lecture des fichiers annexes
    try: df_caisse = pd.read_csv("CaisseMA.csv", sep=None, engine='python')
    except: df_caisse = pd.DataFrame(columns=['Restaurant ID', 'Restaurant Name'])
    
    try: df_new = pd.read_csv("NewRestaurants.csv", sep=None, engine='python')
    except: df_new = pd.DataFrame(columns=['Restaurant ID', 'Restaurant Name'])

    # Gestion Temporelle
    df_merged['order day'] = pd.to_datetime(df_merged['order day'])
    df_merged['Week'] = "Week " + df_merged['order day'].dt.isocalendar().week.astype(str).str.zfill(2)
    semaines_dispos = sorted(df_merged['Week'].unique(), reverse=True)

except Exception as e:
    st.error(f"Erreur fatale de lecture : {e}")
    st.stop()

with st.sidebar:
    st.markdown("### 📅 Filtres Temporels")
    semaine_selectionnee = st.selectbox("Semaine d'analyse", semaines_dispos)
    try: semaine_precedente = semaines_dispos[semaines_dispos.index(semaine_selectionnee) + 1]
    except IndexError: semaine_precedente = None

# ==========================================
# 4. FONCTIONS DE CALCUL (MOTEUR)
# ==========================================
def compute_metrics(df_subset, group_cols):
    return df_subset.groupby(group_cols).agg(
        Requested=('order id', 'count'),
        Delivered=('status', lambda x: (x == 'Delivered').sum()),
        GMV=('item total', lambda x: x[df_subset.loc[x.index, 'status'] == 'Delivered'].sum()),
        CA=('admin earnings', lambda x: x[df_subset.loc[x.index, 'status'] == 'Delivered'].sum()),
        # Nouvelle définition Automation
        Auto_Accepted=('Accepted By', lambda x: x.str.contains('restaurant', case=False, na=False).sum()),
        Cancelled_Total=('status', lambda x: x.str.contains('Cancelled', case=False, na=False).sum())
    ).reset_index()

def compare_wow(df_curr, df_prev, merge_on):
    df_comp = pd.merge(df_curr, df_prev, on=merge_on, suffixes=('', '_prev'), how='left').fillna(0)
    df_comp['Success Rate'] = (df_comp['Delivered'] / df_comp['Requested']).fillna(0)
    df_comp['SR_prev'] = (df_comp['Delivered_prev'] / df_comp['Requested_prev']).fillna(0)
    
    df_comp['WoW Requested'] = df_comp['Requested'] - df_comp['Requested_prev']
    df_comp['WoW Req %'] = (df_comp['Requested'] / df_comp['Requested_prev'] - 1).replace([float('inf'), -float('inf')], 0).fillna(0)
    df_comp['WoW GMV'] = df_comp['GMV'] - df_comp['GMV_prev']
    df_comp['WoW GMV %'] = (df_comp['GMV'] / df_comp['GMV_prev'] - 1).replace([float('inf'), -float('inf')], 0).fillna(0)
    df_comp['WoW SR'] = df_comp['Success Rate'] - df_comp['SR_prev']
    return df_comp

df_current = df_merged[df_merged['Week'] == semaine_selectionnee]
df_prev = df_merged[df_merged['Week'] == semaine_precedente] if semaine_precedente else pd.DataFrame(columns=df_merged.columns)

# ==========================================
# 5. STRUCTURE DES ONGLETS
# ==========================================
tabs = st.tabs([
    "🌍 1. Analyse Global", 
    "📈 2. Overview & Tops/Flops", 
    "❌ 3. Annulations",
    "🤖 4. Automation",
    "💻 5. Caisse.ma",
    "✨ 6. New Restaurants",
    "👻 7. Inactifs"
])

# ----------------------------------------
# ONGLET 1 : ANALYSE GLOBAL
# ----------------------------------------
with tabs[0]:
    st.markdown("#### 🌍 Analyse Macro des Performances")
    
    # KPIs Globaux
    df_macro = compute_metrics(df_merged, ['order day'])
    df_macro = df_macro.sort_values('order day')
    
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        fig_gmv = px.line(df_macro, x="order day", y="GMV", title="Tendance GMV (Daily)", markers=True, template="plotly_white")
        st.plotly_chart(fig_gmv, use_container_width=True)
    with col_chart2:
        fig_req = px.line(df_macro, x="order day", y="Requested", title="Tendance Requested (Daily)", markers=True, template="plotly_white", color_discrete_sequence=['#f39c12'])
        st.plotly_chart(fig_req, use_container_width=True)
    
    st.markdown("---")
    st.markdown("#### 📍 Performances par City & Area")
    
    if 'city' in df_merged.columns and 'Area' in df_merged.columns:
        city_curr = compute_metrics(df_current, ['city'])
        city_prev = compute_metrics(df_prev, ['city'])
        city_comp = compare_wow(city_curr, city_prev, ['city'])
        
        area_curr = compute_metrics(df_current, ['city', 'Area'])
        area_prev = compute_metrics(df_prev, ['city', 'Area'])
        area_comp = compare_wow(area_curr, area_prev, ['city', 'Area'])
        
        col_city, col_area = st.columns(2)
        with col_city:
            st.markdown("**🏙️ Performance City (WoW)**")
            disp_city = city_comp[['city', 'Requested', 'WoW Req %', 'GMV', 'WoW GMV %', 'Success Rate', 'WoW SR']].copy()
            disp_city.style.format({'WoW Req %': '{:+.1%}', 'GMV': '{:,.0f}', 'WoW GMV %': '{:+.1%}', 'Success Rate': '{:.1%}', 'WoW SR': '{:+.1%}'})
            st.dataframe(disp_city, hide_index=True)
            
        with col_area:
            st.markdown("**🏘️ Performance Area (WoW)**")
            disp_area = area_comp[['Area', 'Requested', 'WoW Req %', 'GMV', 'WoW GMV %', 'Success Rate', 'WoW SR']].sort_values('Requested', ascending=False).head(15).copy()
            st.dataframe(disp_area.style.format({'WoW Req %': '{:+.1%}', 'GMV': '{:,.0f}', 'WoW GMV %': '{:+.1%}', 'Success Rate': '{:.1%}', 'WoW SR': '{:+.1%}'}), hide_index=True)
    else:
        st.warning("Colonnes 'city' ou 'Area' introuvables.")

# ----------------------------------------
# ONGLET 2 : OVERVIEW & TOPS / FLOPS
# ----------------------------------------
with tabs[1]:
    st.markdown("#### 📋 Overview & Segments")
    
    resto_curr = compute_metrics(df_current, ['Area', 'Restaurant ID', 'Restaurant Name'])
    resto_prev = compute_metrics(df_prev, ['Area', 'Restaurant ID', 'Restaurant Name'])
    resto_comp = compare_wow(resto_curr, resto_prev, ['Area', 'Restaurant ID', 'Restaurant Name'])
    
    # Tiering A, B, C basé sur le GMV
    try:
        resto_comp['Tier'] = pd.qcut(resto_comp['GMV'].rank(method='first'), q=[0, 0.4, 0.8, 1.0], labels=['Tier C (Low)', 'Tier B (Mid)', 'Tier A (Top)'])
    except:
        resto_comp['Tier'] = "N/A"
    
    # Affichage du Tableau avec Tiering et Acceleration
    disp_resto = resto_comp[['Tier', 'Area', 'Restaurant Name', 'Requested', 'WoW Req %', 'Delivered', 'GMV', 'WoW GMV %', 'Success Rate', 'WoW SR']].copy()
    st.dataframe(disp_resto.sort_values('GMV', ascending=False).style.format({'WoW Req %': '{:+.1%}', 'GMV': '{:,.0f}', 'WoW GMV %': '{:+.1%}', 'Success Rate': '{:.1%}', 'WoW SR': '{:+.1%}'}), use_container_width=True, hide_index=True)
    
    # Intelligence : Anomalies
    anomalies = resto_comp[(resto_comp['Tier'] == 'Tier A (Top)') & (resto_comp['WoW GMV %'] < -0.2)]
    if not anomalies.empty:
        st.error(f"⚠️ **Anomalie détectée :** {len(anomalies)} restaurants Tier A ont perdu plus de 20% de GMV cette semaine !")
    
    # Section Tops & Flops
    st.markdown("---")
    st.markdown("#### 📈 Tops & Flops (Accélération WoW)")
    col_t, col_f = st.columns(2)
    with col_t:
        st.success("🏆 **Top 10 - Croissance GMV**")
        st.dataframe(resto_comp.sort_values('WoW GMV', ascending=False).head(10)[['Restaurant Name', 'WoW GMV', 'WoW GMV %']].style.format({'WoW GMV': '{:,.0f}', 'WoW GMV %': '{:+.1%}'}), hide_index=True)
    with col_f:
        st.error("📉 **Flop 10 - Chute GMV**")
        st.dataframe(resto_comp.sort_values('WoW GMV', ascending=True).head(10)[['Restaurant Name', 'WoW GMV', 'WoW GMV %']].style.format({'WoW GMV': '{:,.0f}', 'WoW GMV %': '{:+.1%}'}), hide_index=True)

# ----------------------------------------
# ONGLET 3 : ANNULATIONS
# ----------------------------------------
with tabs[2]:
    st.markdown("#### ❌ Analyse des Annulations")
    
    df_canc_curr = df_current[df_current['status'].str.contains('Cancelled', case=False, na=False)]
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.markdown("**Comparaison Global vs Périmètres (Area)**")
        if 'Area' in df_canc_curr.columns:
            canc_area = df_canc_curr.groupby('Area').size().reset_index(name='Annulations')
            req_area = df_current.groupby('Area').size().reset_index(name='Total Req')
            m_area = pd.merge(canc_area, req_area, on='Area')
            m_area['% Cancel'] = m_area['Annulations'] / m_area['Total Req']
            st.dataframe(m_area.sort_values('% Cancel', ascending=False).head(10).style.format({'% Cancel': '{:.1%}'}), hide_index=True)
    
    with col_c2:
        st.markdown("**Tendance Annulations (Daily)**")
        canc_trend = df_merged[df_merged['status'].str.contains('Cancelled', case=False, na=False)].groupby('order day').size().reset_index(name='Annulations')
        st.plotly_chart(px.bar(canc_trend, x='order day', y='Annulations'), use_container_width=True)

    st.markdown("---")
    st.markdown("#### 🚨 Les Récidivistes (Pires Taux d'Annulation WoW)")
    
    resto_canc = resto_comp[['Restaurant Name', 'Requested', 'Cancelled_Total', 'Requested_prev', 'Cancelled_Total_prev']].copy()
    resto_canc['Taux Cancel'] = resto_canc['Cancelled_Total'] / resto_canc['Requested']
    resto_canc['Taux Cancel_prev'] = resto_canc['Cancelled_Total_prev'] / resto_canc['Requested_prev']
    resto_canc['WoW Cancel'] = resto_canc['Taux Cancel'] - resto_canc['Taux Cancel_prev']
    
    pires = resto_canc[resto_canc['Requested'] > 10].sort_values('Taux Cancel', ascending=False).head(15)
    st.dataframe(pires.style.format({'Taux Cancel': '{:.1%}', 'Taux Cancel_prev': '{:.1%}', 'WoW Cancel': '{:+.1%}'}), use_container_width=True, hide_index=True)

# ----------------------------------------
# ONGLET 4 : AUTOMATION
# ----------------------------------------
with tabs[3]:
    st.markdown("#### 🤖 Suivi de l'Automatisation")
    st.markdown("*Basé sur la colonne `Accepted By == 'restaurant'`*")
    
    df_current['Is_Auto'] = df_current['Accepted By'].str.contains('restaurant', case=False, na=False)
    
    auto_recap = df_current.groupby('Is_Auto').agg(
        Requested=('order id', 'count'),
        Delivered=('status', lambda x: (x == 'Delivered').sum()),
        GMV=('item total', lambda x: x[df_current.loc[x.index, 'status'] == 'Delivered'].sum())
    ).reset_index()
    auto_recap['Success Rate'] = auto_recap['Delivered'] / auto_recap['Requested']
    auto_recap['Type'] = auto_recap['Is_Auto'].map({True: '🤖 Automatisé (Restaurant)', False: '👨‍💻 Manuel (Autre)'})
    
    st.markdown("**📊 Performance Automatisé vs Non-Automatisé**")
    st.dataframe(auto_recap[['Type', 'Requested', 'Delivered', 'Success Rate', 'GMV']].style.format({'Success Rate': '{:.1%}', 'GMV': '{:,.0f}'}), hide_index=True)

# ----------------------------------------
# ONGLET 5 : CAISSE.MA
# ----------------------------------------
with tabs[4]:
    st.markdown("#### 💻 Intégration Caisse.ma")
    if df_caisse.empty:
        st.warning("Fichier `CaisseMA.csv` introuvable.")
    else:
        df_caisse_comp = resto_comp[resto_comp['Restaurant ID'].isin(df_caisse['Restaurant ID'])]
        st.dataframe(df_caisse_comp[['Restaurant Name', 'Requested', 'WoW Req %', 'GMV', 'WoW GMV %', 'Success Rate', 'WoW SR']].style.format({'WoW Req %': '{:+.1%}', 'GMV': '{:,.0f}', 'WoW GMV %': '{:+.1%}', 'Success Rate': '{:.1%}', 'WoW SR': '{:+.1%}'}), hide_index=True, use_container_width=True)

# ----------------------------------------
# ONGLET 6 : NEW RESTAURANTS
# ----------------------------------------
with tabs[5]:
    st.markdown("#### ✨ Performances Nouveaux Restaurants")
    if df_new.empty:
        st.warning("Fichier `NewRestaurants.csv` introuvable.")
    else:
        df_new_comp = resto_comp[resto_comp['Restaurant ID'].isin(df_new['Restaurant ID'])]
        st.markdown("**KPIs & Opérations de Livraison**")
        st.dataframe(df_new_comp[['Restaurant Name', 'Requested', 'Delivered', 'Success Rate', 'GMV']].style.format({'Success Rate': '{:.1%}', 'GMV': '{:,.0f}'}), hide_index=True, use_container_width=True)

# ----------------------------------------
# ONGLET 7 : INACTIFS
# ----------------------------------------
with tabs[6]:
    st.markdown("#### 👻 Surveillances des Inactifs (Zero Commandes)")
    
    jours_inactifs = st.radio("Seuil d'inactivité :", [3, 7, 15, 30, 90], format_func=lambda x: f"Derniers {x} jours", horizontal=True)
    
    max_date = df_merged['order day'].max()
    threshold_date = max_date - timedelta(days=jours_inactifs)
    
    # Commandes dans la fenêtre
    df_window = df_merged[df_merged['order day'] >= threshold_date]
    restos_actifs = df_window['Restaurant ID'].unique()
    
    # Comparaison avec la liste attendue (Config complète)
    restos_inactifs = liste_attendue[~liste_attendue['Restaurant ID'].isin(restos_actifs)]
    
    st.error(f"⚠️ **{len(restos_inactifs)} restaurants** n'ont reçu aucune commande sur les {jours_inactifs} derniers jours !")
    st.dataframe(restos_inactifs[['Restaurant Name', 'Restaurant ID']], hide_index=True, use_container_width=True)
