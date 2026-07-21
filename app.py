import streamlit as st
import pandas as pd
import plotly.express as px

# ==========================================
# 1. CONFIGURATION DE LA PAGE
# ==========================================
st.set_page_config(page_title="Yassir Performance", page_icon="🍔", layout="wide")

# ==========================================
# 2. EN-TÊTE ET CONTRÔLES (AVEC SWITCH GLOBAL)
# ==========================================
st.title("📊 Dashboard Performances Yassir")
st.markdown("---")

st.markdown("### ⚙️ Configuration & Données")

# Choix de la portée d'analyse (Global ou par AM)
vue_globale = st.radio("Portée de l'analyse :", ["🇲🇦 Global Maroc", "🎯 Par Account Manager (Pipeline)"], horizontal=True)

col_am, col_upload = st.columns([1, 2])

with col_am:
    if vue_globale == "🎯 Par Account Manager (Pipeline)":
        am_choisi = st.selectbox("Pipeline", ["Houda", "Yassine", "Sara", "Amine"], label_visibility="collapsed")
        st.caption(f"📂 Config lue : `Pipeline - {am_choisi}.csv`")
    else:
        am_choisi = "Global"
        st.caption("🌍 Analyse sur l'intégralité du pays.")

with col_upload:
    fichier_data = st.file_uploader("Upload Data (admin-earnings...csv)", type=["csv", "xlsx"], label_visibility="collapsed")

st.markdown("---")

if fichier_data is None:
    st.info("👋 Veuillez uploader le fichier Data de la semaine pour générer le tableau de bord.")
    st.stop()

# ==========================================
# 3. MOTEUR DE DONNÉES ET PRÉPARATION
# ==========================================
try:
    # 3.1 Lecture de la donnée brute
    df_data = pd.read_csv(fichier_data)
    
    # Standardisation du nom de la colonne restaurant pour faciliter les jointures
    if "restaurant name" in df_data.columns and "Restaurant Name" not in df_data.columns:
        df_data.rename(columns={"restaurant name": "Restaurant Name"}, inplace=True)

    # 3.2 Filtrage selon le choix Global ou Pipeline
    if vue_globale == "🎯 Par Account Manager (Pipeline)":
        df_pipeline = pd.read_csv(f"Pipeline - {am_choisi}.csv", sep=None, engine='python')
        df_merged = pd.merge(df_data, df_pipeline, on="Restaurant ID", how="inner")
    else:
        df_merged = df_data.copy()
        if 'Segment' not in df_merged.columns:
            df_merged['Segment'] = 'Global' # Valeur par défaut si on est en vue globale

    # 3.3 Lecture du fichier d'intégration Caisse.ma
    try:
        df_caisse = pd.read_csv("CaisseMA.csv", sep=None, engine='python')
    except:
        # Fichier vide ou non trouvé en sécurité
        df_caisse = pd.DataFrame(columns=['Restaurant ID', 'Restaurant Name'])

    # 3.4 Création des dates et semaines
    df_merged['order day'] = pd.to_datetime(df_merged['order day'])
    df_merged['Week'] = "Week " + df_merged['order day'].dt.isocalendar().week.astype(str).str.zfill(2)

    semaines_dispos = sorted(df_merged['Week'].unique(), reverse=True)

except Exception as e:
    st.error(f"Erreur de lecture des données : {e}")
    st.stop()

with st.sidebar:
    st.markdown("### 📅 Filtres Temporels")
    semaine_selectionnee = st.selectbox("Semaine d'analyse", semaines_dispos)
    
    try:
        index_semaine = semaines_dispos.index(semaine_selectionnee)
        semaine_precedente = semaines_dispos[index_semaine + 1]
    except IndexError:
        semaine_precedente = None

# ==========================================
# 4. PRÉ-CALCUL DES PERFORMANCES PAR RESTAURANT (Moteur WoW)
# ==========================================
# Nous le calculons ici pour pouvoir le réutiliser dans les onglets Pipeline, Tops et Caisse.ma
def compute_metrics(df_week):
    # On intègre le Restaurant ID pour pouvoir faire la jointure Caisse.ma plus tard
    return df_week.groupby(['Area', 'Restaurant ID', 'Restaurant Name']).agg(
        Requested=('order id', 'count'),
        Delivered=('status', lambda x: (x == 'Delivered').sum()),
        CancelledByRestaurant=('status', lambda x: x.str.contains('restaurant', case=False, na=False).sum()),
        GMV=('item total', lambda x: x[df_week.loc[x.index, 'status'] == 'Delivered'].sum()),
        CA=('admin earnings', lambda x: x[df_week.loc[x.index, 'status'] == 'Delivered'].sum()),
        Commission=('restaurant commission', lambda x: x[df_week.loc[x.index, 'status'] == 'Delivered'].sum()),
        Promo_Restaurant=('coupon restaurant', 'sum'),
        Promo_Admin=('coupon admin', 'sum'),
        LR_LG_Costs=('driver payout', 'sum')
    ).reset_index()

df_current = df_merged[df_merged['Week'] == semaine_selectionnee]
metrics_current = compute_metrics(df_current)

metrics_current['Success Rate'] = (metrics_current['Delivered'] / metrics_current['Requested']).fillna(0)
metrics_current['AcceptedByRestaurant'] = metrics_current['Requested'] - metrics_current['CancelledByRestaurant']
metrics_current['Taux Acceptation'] = (metrics_current['AcceptedByRestaurant'] / metrics_current['Requested']).fillna(0)
metrics_current['Taux Cancellation'] = (metrics_current['CancelledByRestaurant'] / metrics_current['Requested']).fillna(0)
metrics_current['AOV'] = (metrics_current['GMV'] / metrics_current['Delivered']).fillna(0)
metrics_current['Semaine'] = semaine_selectionnee

if semaine_precedente:
    df_prev = df_merged[df_merged['Week'] == semaine_precedente]
    metrics_prev = compute_metrics(df_prev)
    metrics_prev['AcceptedByRestaurant'] = metrics_prev['Requested'] - metrics_prev['CancelledByRestaurant']
    metrics_prev['Taux Acceptation'] = (metrics_prev['AcceptedByRestaurant'] / metrics_prev['Requested']).fillna(0)
    metrics_prev['Taux Cancellation'] = (metrics_prev['CancelledByRestaurant'] / metrics_prev['Requested']).fillna(0)
    metrics_prev['AOV'] = (metrics_prev['GMV'] / metrics_prev['Delivered']).fillna(0)
    
    df_compare = pd.merge(metrics_current, metrics_prev, on=['Area', 'Restaurant ID', 'Restaurant Name'], suffixes=('', '_prev'), how='left')
    
    df_compare['wow delivered'] = df_compare['Delivered'] - df_compare['Delivered_prev'].fillna(0)
    df_compare['wow delivered %'] = (df_compare['Delivered'] / df_compare['Delivered_prev'] - 1).fillna(0)
    df_compare['wow T.A'] = df_compare['Taux Acceptation'] - df_compare['Taux Acceptation_prev'].fillna(0)
    df_compare['wow Cancellation'] = df_compare['Taux Cancellation'] - df_compare['Taux Cancellation_prev'].fillna(0)
    df_compare['wow GMV'] = df_compare['GMV'] - df_compare['GMV_prev'].fillna(0)
    df_compare['Wow CA'] = df_compare['CA'] - df_compare['CA_prev'].fillna(0)
    df_compare['Wow AOV'] = df_compare['AOV'] - df_compare['AOV_prev'].fillna(0)
    df_compare['Wow Promo Order'] = (df_compare['Promo_Restaurant'] + df_compare['Promo_Admin']) - (df_compare['Promo_Restaurant_prev'].fillna(0) + df_compare['Promo_Admin_prev'].fillna(0))
    df_compare['Wow LR_LG_Costs'] = df_compare['LR_LG_Costs'] - df_compare['LR_LG_Costs_prev'].fillna(0)
else:
    df_compare = metrics_current.copy()
    for col in ['wow delivered', 'wow delivered %', 'wow T.A', 'wow Cancellation', 'wow GMV', 'Wow CA', 'Wow AOV', 'Wow Promo Order', 'Wow LR_LG_Costs']:
        df_compare[col] = 0
        df_compare[col.replace('wow ', '') + '_prev'] = 0

colonnes_finales = [
    'Area', 'Restaurant Name', 'Semaine', 'Requested', 'Delivered', 'Success Rate', 
    'AcceptedByRestaurant', 'Taux Acceptation', 'CancelledByRestaurant', 'Taux Cancellation', 
    'GMV', 'AOV', 'Commission', 'Promo_Restaurant', 'Promo_Admin', 'LR_LG_Costs',
    'wow delivered', 'wow delivered %', 'wow T.A', 'wow Cancellation', 
    'wow GMV', 'Wow CA', 'Wow AOV', 'Wow Promo Order', 'Wow LR_LG_Costs'
]

# ==========================================
# 5. STRUCTURE DES ONGLETS
# ==========================================
tab_global, tab_pipeline, tab_flops, tab_annulations, tab_automation, tab_caisse = st.tabs([
    "🌍 Analyse Global", 
    "📈 Overview Pipeline", 
    "🚨 Tops & Flops", 
    "❌ Annulations",
    "🤖 Automation",
    "💻 Intégration Caisse.ma"
])

# ----------------------------------------
# ONGLET 1 : ANALYSE GLOBAL
# ----------------------------------------
with tab_global:
    st.markdown(f"#### 🌍 Analyse Macro des Performances ({am_choisi})")
    
    vue_temporelle = st.radio("Vue temporelle :", ["📅 Jour", "📊 Week over Week (WoW)"], horizontal=True)
    st.markdown("---")
    
    if vue_temporelle == "📅 Jour":
        df_merged['Période'] = df_merged['order day'].dt.strftime('%Y-%m-%d')
    else:
        df_merged['Période'] = df_merged['Week']

    df_macro = df_merged.groupby('Période').agg(
        Reçu=('order id', 'count'),
        Livré=('status', lambda x: (x == 'Delivered').sum()),
        GMV=('item total', lambda x: x[df_merged.loc[x.index, 'status'] == 'Delivered'].sum()),
        CA=('admin earnings', lambda x: x[df_merged.loc[x.index, 'status'] == 'Delivered'].sum())
    ).reset_index()

    df_macro['AOV'] = (df_macro['GMV'] / df_macro['Livré']).fillna(0)
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
    
    fig_macro = px.line(df_macro, x="Période", y="GMV", title="Tendance GMV", markers=True, template="plotly_white")
    st.plotly_chart(fig_macro, use_container_width=True)

# ----------------------------------------
# ONGLET 2 : OVERVIEW PIPELINE
# ----------------------------------------
with tab_pipeline:
    st.markdown(f"#### 📋 Tableau Détaillé ({semaine_selectionnee} - {am_choisi})")
    
    df_pipeline_display = df_compare[colonnes_finales].copy()
    
    for col in ['Success Rate', 'Taux Acceptation', 'Taux Cancellation', 'wow delivered %', 'wow T.A', 'wow Cancellation']:
        df_pipeline_display[col] = df_pipeline_display[col].apply(lambda x: f"{x:+.1%}")
    for col in ['GMV', 'AOV', 'Commission', 'Promo_Restaurant', 'Promo_Admin', 'LR_LG_Costs', 'wow GMV', 'Wow CA', 'Wow AOV', 'Wow Promo Order', 'Wow LR_LG_Costs']:
        df_pipeline_display[col] = df_pipeline_display[col].apply(lambda x: f"{x:,.1f}")

    st.dataframe(df_pipeline_display, use_container_width=True, hide_index=True)

# ----------------------------------------
# ONGLET 3 : TOPS & FLOPS
# ----------------------------------------
with tab_flops:
    st.markdown("#### 📉 Classement des variations WoW (Delivered)")
    col_top, col_flop = st.columns(2)
    
    with col_top:
        st.success("**🏆 Top 10 - Plus fortes progressions**")
        top_10 = df_compare.sort_values(by="wow delivered", ascending=False).head(10)
        st.dataframe(top_10[['Restaurant Name', 'Area', 'wow delivered', 'wow delivered %']].style.format({"wow delivered %": "{:+.1%}"}), hide_index=True, use_container_width=True)
        
    with col_flop:
        st.error("**⚠️ Flop 10 - Plus fortes baisses (Drops)**")
        flop_10 = df_compare.sort_values(by="wow delivered", ascending=True).head(10)
        st.dataframe(flop_10[['Restaurant Name', 'Area', 'wow delivered', 'wow delivered %']].style.format({"wow delivered %": "{:+.1%}"}), hide_index=True, use_container_width=True)

# ----------------------------------------
# ONGLET 4 : ANNULATIONS
# ----------------------------------------
with tab_annulations:
    st.markdown(f"#### ❌ Analyse des Annulations ({semaine_selectionnee})")
    df_cancelled = df_current[df_current['status'].str.contains('Cancelled', case=False, na=False)]
    
    if not df_cancelled.empty:
        cancel_reasons = df_cancelled['cancellation reason '].value_counts().reset_index()
        cancel_reasons.columns = ['Raison', 'Nombre']
        
        col_chart, col_table = st.columns([2, 1])
        with col_chart:
            fig_pie = px.pie(cancel_reasons, values='Nombre', names='Raison', title="Motifs d'annulation", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)
        with col_table:
            st.dataframe(cancel_reasons, hide_index=True, use_container_width=True)
    else:
        st.success("🎉 Aucune annulation sur cette semaine !")

# ----------------------------------------
# ONGLET 5 : AUTOMATION
# ----------------------------------------
with tab_automation:
    st.markdown(f"#### 🤖 Suivi de l'Automatisation ({semaine_selectionnee})")
    col_recap1, col_recap2, col_recap3 = st.columns(3)
    
    tot_req = df_compare['Requested'].sum()
    tot_acc = df_compare['AcceptedByRestaurant'].sum()
    ta_global = tot_acc / tot_req if tot_req > 0 else 0
    
    if semaine_precedente:
        tot_req_prev = df_compare['Requested_prev'].sum()
        tot_acc_prev = df_compare['AcceptedByRestaurant_prev'].sum()
        ta_global_prev = tot_acc_prev / tot_req_prev if tot_req_prev > 0 else 0
    else:
        tot_req_prev, tot_acc_prev, ta_global_prev = 0, 0, 0
        
    wow_ta_global = ta_global - ta_global_prev
    
    col_recap1.metric("Commandes Reçues", f"{tot_req:,.0f}", f"{(tot_req - tot_req_prev):+,.0f} WoW")
    col_recap2.metric("Commandes Acceptées", f"{tot_acc:,.0f}", f"{(tot_acc - tot_acc_prev):+,.0f} WoW")
    col_recap3.metric("Taux d'Acceptation", f"{ta_global:.1%}", f"{wow_ta_global:+.1%} WoW")
    st.markdown("---")
    
    col_acc, col_reg = st.columns(2)
    cols_to_show = ['Restaurant Name', 'Area', 'Requested', 'Taux Acceptation_prev', 'Taux Acceptation', 'wow T.A']
    
    with col_acc:
        st.success("**🚀 Top Accélérations T.A**")
        df_acc = df_compare[df_compare['wow T.A'] > 0].sort_values('wow T.A', ascending=False).head(15)
        df_acc_disp = df_acc[cols_to_show].copy()
        df_acc_disp['Taux Acceptation_prev'] = df_acc_disp['Taux Acceptation_prev'].apply(lambda x: f"{x:.1%}")
        df_acc_disp['Taux Acceptation'] = df_acc_disp['Taux Acceptation'].apply(lambda x: f"{x:.1%}")
        df_acc_disp['wow T.A'] = df_acc_disp['wow T.A'].apply(lambda x: f"{x:+.1%}")
        st.dataframe(df_acc_disp, hide_index=True, use_container_width=True)

    with col_reg:
        st.error("**⚠️ Pires Régressions T.A**")
        df_reg = df_compare[df_compare['wow T.A'] < 0].sort_values('wow T.A', ascending=True).head(15)
        df_reg_disp = df_reg[cols_to_show].copy()
        df_reg_disp['Taux Acceptation_prev'] = df_reg_disp['Taux Acceptation_prev'].apply(lambda x: f"{x:.1%}")
        df_reg_disp['Taux Acceptation'] = df_reg_disp['Taux Acceptation'].apply(lambda x: f"{x:.1%}")
        df_reg_disp['wow T.A'] = df_reg_disp['wow T.A'].apply(lambda x: f"{x:+.1%}")
        st.dataframe(df_reg_disp, hide_index=True, use_container_width=True)

# ----------------------------------------
# ONGLET 6 : CAISSE.MA (NOUVEAU)
# ----------------------------------------
with tab_caisse:
    st.markdown("#### 💻 Performances des Intégrations (Caisse.ma)")
    st.markdown("Analyse isolée des restaurants utilisant l'agrégateur de commandes.")
    
    if df_caisse.empty:
        st.warning("⚠️ Fichier `CaisseMA.csv` introuvable ou vide. Uploadez-le sur GitHub pour activer cet onglet.")
    else:
        # On filtre la donnée globale pour ne garder que les restos Caisse.ma
        df_compare_caisse = df_compare[df_compare['Restaurant ID'].isin(df_caisse['Restaurant ID'])]
        
        if df_compare_caisse.empty:
            st.info("Aucun restaurant de la vue actuelle n'est équipé de Caisse.ma.")
        else:
            # --- KPIs Caisse.ma ---
            st.markdown("##### 🏆 Vue d'ensemble Caisse.ma")
            col_kpi_c1, col_kpi_c2, col_kpi_c3 = st.columns(3)
            
            tot_req_caisse = df_compare_caisse['Requested'].sum()
            tot_acc_caisse = df_compare_caisse['AcceptedByRestaurant'].sum()
            ta_caisse = tot_acc_caisse / tot_req_caisse if tot_req_caisse > 0 else 0
            
            if semaine_precedente:
                tot_req_prev_caisse = df_compare_caisse['Requested_prev'].sum()
                tot_acc_prev_caisse = df_compare_caisse['AcceptedByRestaurant_prev'].sum()
                ta_prev_caisse = tot_acc_prev_caisse / tot_req_prev_caisse if tot_req_prev_caisse > 0 else 0
            else:
                tot_req_prev_caisse, tot_acc_prev_caisse, ta_prev_caisse = 0, 0, 0
                
            col_kpi_c1.metric("Restaurants Équipés", len(df_compare_caisse))
            col_kpi_c2.metric("Taux d'Acceptation Moyen", f"{ta_caisse:.1%}", f"{(ta_caisse - ta_prev_caisse):+.1%} WoW")
            
            # Comparatif avec le reste de la plateforme (ROI)
            ta_autres = (tot_acc - tot_acc_caisse) / (tot_req - tot_req_caisse) if (tot_req - tot_req_caisse) > 0 else 0
            diff_ta = ta_caisse - ta_autres
            col_kpi_c3.metric("Différentiel vs Non-Équipés", f"{diff_ta:+.1%} vs Autres", delta_color="normal")
            
            st.markdown("---")
            
            # --- Tableau Détaillé Caisse.ma ---
            st.markdown("##### 📋 Tableau Détaillé des Intégrations")
            df_caisse_display = df_compare_caisse[colonnes_finales].copy()
            
            for col in ['Success Rate', 'Taux Acceptation', 'Taux Cancellation', 'wow delivered %', 'wow T.A', 'wow Cancellation']:
                df_caisse_display[col] = df_caisse_display[col].apply(lambda x: f"{x:+.1%}")
            for col in ['GMV', 'AOV', 'Commission', 'Promo_Restaurant', 'Promo_Admin', 'LR_LG_Costs', 'wow GMV', 'Wow CA', 'Wow AOV', 'Wow Promo Order', 'Wow LR_LG_Costs']:
                df_caisse_display[col] = df_caisse_display[col].apply(lambda x: f"{x:,.1f}")

            st.dataframe(df_caisse_display, use_container_width=True, hide_index=True)
            
            # --- Graphique d'impact ---
            st.markdown("##### 📉 Taux d'Acceptation des intégrés")
            fig_caisse = px.bar(df_compare_caisse.sort_values(by="Taux Acceptation", ascending=False), 
                                x="Restaurant Name", y="Taux Acceptation", color="Area", 
                                title="Performance T.A par Partenaire Intégré")
            st.plotly_chart(fig_caisse, use_container_width=True)
