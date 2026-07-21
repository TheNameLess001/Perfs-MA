import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
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
# 3. MOTEUR DE DONNÉES (CORRECTION DU BUG)
# ==========================================
try:
    df_data = pd.read_csv(fichier_data)
    
    # On standardise le nom du restaurant dans la data brute
    if "restaurant name" in df_data.columns:
        df_data.rename(columns={"restaurant name": "Restaurant Name"}, inplace=True)

    if vue_globale == "🎯 Par Account Manager (Pipeline)":
        df_pipeline = pd.read_csv(f"Pipeline - {am_choisi}.csv", sep=None, engine='python')
        # Pour éviter le bug du KeyError (_x et _y), on supprime le nom de la data brute s'il est déjà dans la config
        if 'Restaurant Name' in df_data.columns and 'Restaurant Name' in df_pipeline.columns:
            df_data.drop(columns=['Restaurant Name'], inplace=True)
            
        df_merged = pd.merge(df_data, df_pipeline, on="Restaurant ID", how="inner")
        liste_attendue = df_pipeline[['Restaurant ID', 'Restaurant Name']].drop_duplicates()
    else:
        df_merged = df_data.copy()
        df_merged['Segment'] = 'Global'
        liste_attendue = df_merged[['Restaurant ID', 'Restaurant Name']].drop_duplicates()

    # Fichiers annexes
    try: df_caisse = pd.read_csv("CaisseMA.csv", sep=None, engine='python')
    except: df_caisse = pd.DataFrame(columns=['Restaurant ID', 'Restaurant Name'])
    
    try: df_new = pd.read_csv("NewRestaurants.csv", sep=None, engine='python')
    except: df_new = pd.DataFrame(columns=['Restaurant ID', 'Restaurant Name'])

    # Gestion des dates
    df_merged['order day'] = pd.to_datetime(df_merged['order day'])
    df_merged['Week'] = "Week " + df_merged['order day'].dt.isocalendar().week.astype(str).str.zfill(2)
    semaines_dispos = sorted(df_merged['Week'].unique(), reverse=True)

except Exception as e:
    st.error(f"Erreur de lecture du fichier : {e}")
    st.stop()

with st.sidebar:
    st.markdown("### 📅 Filtres Temporels")
    semaine_selectionnee = st.selectbox("Semaine courante", semaines_dispos)
    try: semaine_precedente = semaines_dispos[semaines_dispos.index(semaine_selectionnee) + 1]
    except IndexError: semaine_precedente = None

# ==========================================
# 4. FONCTIONS DE CALCUL & WOW (MOTEUR)
# ==========================================
def compute_metrics(df_subset, group_cols):
    return df_subset.groupby(group_cols).agg(
        Requested=('order id', 'count'),
        Delivered=('status', lambda x: (x == 'Delivered').sum()),
        # AUTOMATION CORRIGÉE : On cherche "restaurant" dans la colonne "Accepted By"
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
    
    # Taux Actuels
    df_comp['Success Rate'] = (df_comp['Delivered'] / df_comp['Requested']).fillna(0)
    df_comp['Taux Acceptation'] = (df_comp['Auto_Accepted'] / df_comp['Requested']).fillna(0)
    df_comp['Taux Cancellation'] = (df_comp['CancelledByRestaurant'] / df_comp['Requested']).fillna(0)
    df_comp['AOV'] = (df_comp['GMV'] / df_comp['Delivered']).fillna(0)
    
    # Taux Précédents
    sr_prev = (df_comp['Delivered_prev'] / df_comp['Requested_prev']).fillna(0)
    ta_prev = (df_comp['Auto_Accepted_prev'] / df_comp['Requested_prev']).fillna(0)
    tc_prev = (df_comp['CancelledByRestaurant_prev'] / df_comp['Requested_prev']).fillna(0)
    
    # Calculs WoW
    df_comp['wow delivered'] = df_comp['Delivered'] - df_comp['Delivered_prev']
    df_comp['wow delivered %'] = (df_comp['Delivered'] / df_comp['Delivered_prev'] - 1).replace([np.inf, -np.inf], 0).fillna(0)
    df_comp['wow T.A'] = df_comp['Taux Acceptation'] - ta_prev
    df_comp['wow Cancellation'] = df_comp['Taux Cancellation'] - tc_prev
    df_comp['wow GMV'] = df_comp['GMV'] - df_comp['GMV_prev']
    df_comp['Wow CA'] = df_comp['CA'] - df_comp['CA_prev']
    df_comp['Wow AOV'] = df_comp['AOV'] - (df_comp['GMV_prev'] / df_comp['Delivered_prev']).fillna(0)
    df_comp['Wow Promo Order'] = (df_comp['Promo_Restaurant'] + df_comp['Promo_Admin']) - (df_comp['Promo_Restaurant_prev'] + df_comp['Promo_Admin_prev'])
    df_comp['Wow LR_LG_Costs'] = df_comp['LR_LG_Costs'] - df_comp['LR_LG_Costs_prev']
    
    # Segmentation par Tier (A, B, C) selon le GMV actuel
    if not df_comp.empty and 'GMV' in df_comp.columns:
        df_comp['Tier'] = pd.qcut(df_comp['GMV'].rank(method='first'), q=[0, 0.4, 0.8, 1.0], labels=['Tier C', 'Tier B', 'Tier A'])
    else:
        df_comp['Tier'] = "N/A"
        
    return df_comp

df_current = df_merged[df_merged['Week'] == semaine_selectionnee]
df_prev = df_merged[df_merged['Week'] == semaine_precedente] if semaine_precedente else pd.DataFrame(columns=df_merged.columns)

# ==========================================
# 5. STRUCTURE DES ONGLETS
# ==========================================
tabs = st.tabs([
    "🌍 1. Analyse Global", 
    "📈 2. Overview Pipeline & Tops", 
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
    st.markdown("#### 🌍 Analyse Macro & Tendances")
    
    # 1.1 Courbes de Tendance
    df_daily = compute_metrics(df_merged, ['order day']).sort_values('order day')
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.plotly_chart(px.line(df_daily, x="order day", y="GMV", title="Tendance GMV", markers=True), use_container_width=True)
    with col_g2:
        st.plotly_chart(px.line(df_daily, x="order day", y="Requested", title="Tendance Commandes Reçues", markers=True, color_discrete_sequence=['#f39c12']), use_container_width=True)
        
    st.markdown("---")
    
    # 1.2 Tableaux City & Area
    if 'city' in df_merged.columns and 'Area' in df_merged.columns:
        city_curr, city_prev = compute_metrics(df_current, ['city']), compute_metrics(df_prev, ['city'])
        city_comp = compare_wow(city_curr, city_prev, ['city'])
        
        area_curr, area_prev = compute_metrics(df_current, ['city', 'Area']), compute_metrics(df_prev, ['city', 'Area'])
        area_comp = compare_wow(area_curr, area_prev, ['city', 'Area'])
        
        col_city, col_area = st.columns(2)
        with col_city:
            st.markdown("##### 🏙️ Performances par Ville")
            disp_city = city_comp[['city', 'Requested', 'wow delivered %', 'GMV', 'wow GMV', 'Success Rate', 'wow T.A']].copy()
            st.dataframe(disp_city.style.format({'wow delivered %': '{:+.1%}', 'GMV': '{:,.0f}', 'wow GMV': '{:+,.0f}', 'Success Rate': '{:.1%}', 'wow T.A': '{:+.1%}'}), hide_index=True)
            st.plotly_chart(px.bar(city_comp, x='city', y='GMV', title="Poids des villes (GMV)"), use_container_width=True)
            
        with col_area:
            st.markdown("##### 🏘️ Performances par Zone (Area)")
            disp_area = area_comp[['Area', 'Requested', 'wow delivered %', 'GMV', 'wow GMV', 'Success Rate', 'wow T.A']].sort_values('Requested', ascending=False).head(15).copy()
            st.dataframe(disp_area.style.format({'wow delivered %': '{:+.1%}', 'GMV': '{:,.0f}', 'wow GMV': '{:+,.0f}', 'Success Rate': '{:.1%}', 'wow T.A': '{:+.1%}'}), hide_index=True)
            st.plotly_chart(px.bar(disp_area, x='Area', y='Requested', title="Zones les plus actives"), use_container_width=True)

# ----------------------------------------
# ONGLET 2 : OVERVIEW PIPELINE & TOPS/FLOPS
# ----------------------------------------
with tabs[1]:
    st.markdown("#### 📋 Base de Données Détaillée & Anomalies")
    
    resto_curr, resto_prev = compute_metrics(df_current, ['Area', 'Restaurant ID', 'Restaurant Name']), compute_metrics(df_prev, ['Area', 'Restaurant ID', 'Restaurant Name'])
    resto_comp = compare_wow(resto_curr, resto_prev, ['Area', 'Restaurant ID', 'Restaurant Name'])
    
    # 2.1 Le Grand Tableau Restauré
    cols_big_table = [
        'Tier', 'Area', 'Restaurant Name', 'Requested', 'Delivered', 'Success Rate', 
        'Auto_Accepted', 'Taux Acceptation', 'CancelledByRestaurant', 'Taux Cancellation', 
        'GMV', 'AOV', 'Commission', 'Promo_Restaurant', 'Promo_Admin', 'LR_LG_Costs',
        'wow delivered', 'wow delivered %', 'wow T.A', 'wow Cancellation', 
        'wow GMV', 'Wow CA', 'Wow AOV', 'Wow Promo Order', 'Wow LR_LG_Costs'
    ]
    df_pipeline_display = resto_comp[cols_big_table].copy()
    
    for c in ['Success Rate', 'Taux Acceptation', 'Taux Cancellation', 'wow delivered %', 'wow T.A', 'wow Cancellation']:
        df_pipeline_display[c] = df_pipeline_display[c].apply(lambda x: f"{x:+.1%}")
    for c in ['GMV', 'AOV', 'Commission', 'Promo_Restaurant', 'Promo_Admin', 'LR_LG_Costs', 'wow GMV', 'Wow CA', 'Wow AOV', 'Wow Promo Order', 'Wow LR_LG_Costs']:
        df_pipeline_display[c] = df_pipeline_display[c].apply(lambda x: f"{x:,.1f}")

    st.dataframe(df_pipeline_display, use_container_width=True, hide_index=True)
    
    # 2.2 Alertes Tier A
    anomalies = resto_comp[(resto_comp['Tier'] == 'Tier A') & (resto_comp['wow delivered %'] < -0.15)]
    if not anomalies.empty:
        st.error(f"🚨 **ALERTE BUSINESS :** {len(anomalies)} restaurants du 'Tier A' (les plus gros) ont subi une baisse de plus de 15% de leurs commandes cette semaine !")
        st.dataframe(anomalies[['Restaurant Name', 'Area', 'Requested', 'wow delivered %', 'wow GMV']].style.format({'wow delivered %': '{:+.1%}', 'wow GMV': '{:+,.0f}'}), hide_index=True)

    st.markdown("---")
    
    # 2.3 Tops & Flops
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
            st.plotly_chart(px.pie(reasons, names='Motif', values='Nombre', hole=0.4), use_container_width=True)

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
    
    # Résumé Automatisé vs Non-Automatisé
    if 'Accepted By' in df_current.columns:
        df_current['Is_Auto'] = df_current['Accepted By'].str.contains('restaurant', case=False, na=False)
        auto_recap = df_current.groupby('Is_Auto').agg(
            Requested=('order id', 'count'),
            Delivered=('status', lambda x: (x == 'Delivered').sum()),
            GMV=('item total', lambda x: x[df_current.loc[x.index, 'status'] == 'Delivered'].sum())
        ).reset_index()
        auto_recap['Success Rate'] = auto_recap['Delivered'] / auto_recap['Requested']
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
    st.markdown("#### 💻 Intégration Caisse.ma")
    if df_caisse.empty:
        st.warning("Fichier `CaisseMA.csv` introuvable.")
    else:
        df_caisse_comp = resto_comp[resto_comp['Restaurant ID'].isin(df_caisse['Restaurant ID'])]
        if df_caisse_comp.empty:
            st.info("Aucun restaurant de cette vue n'est équipé.")
        else:
            st.dataframe(df_caisse_comp[['Restaurant Name', 'Area', 'Requested', 'wow delivered %', 'GMV', 'wow GMV %', 'Taux Acceptation', 'Success Rate']].style.format({
                'wow delivered %': '{:+.1%}', 'GMV': '{:,.0f}', 'wow GMV %': '{:+.1%}', 'Taux Acceptation': '{:.1%}', 'Success Rate': '{:.1%}'
            }), hide_index=True, use_container_width=True)

# ----------------------------------------
# ONGLET 6 : NEW RESTAURANTS
# ----------------------------------------
with tabs[5]:
    st.markdown("#### ✨ Performances Nouveaux Restaurants")
    if df_new.empty:
        st.warning("Fichier `NewRestaurants.csv` introuvable.")
    else:
        df_new_comp = resto_comp[resto_comp['Restaurant ID'].isin(df_new['Restaurant ID'])]
        st.dataframe(df_new_comp[['Restaurant Name', 'Area', 'Requested', 'Delivered', 'Success Rate', 'Taux Acceptation', 'GMV', 'wow GMV']].style.format({
            'Success Rate': '{:.1%}', 'Taux Acceptation': '{:.1%}', 'GMV': '{:,.0f}', 'wow GMV': '{:+,.0f}'
        }), hide_index=True, use_container_width=True)

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
        st.success(f"Tous les restaurants de votre pipeline ont reçu au moins 1 commande ces {jours_inactifs} derniers jours !")
    else:
        st.error(f"⚠️ **{len(restos_inactifs)} restaurants** de votre config n'ont reçu aucune commande depuis {jours_inactifs} jours !")
        st.dataframe(restos_inactifs[['Restaurant Name']], hide_index=True, use_container_width=True)
