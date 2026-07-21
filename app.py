import streamlit as st
import pandas as pd
import plotly.express as px

# ==========================================
# 1. CONFIGURATION DE LA PAGE
# ==========================================
st.set_page_config(page_title="Yassir Performance", page_icon="🍔", layout="wide")

# ==========================================
# 2. EN-TÊTE ET CONTRÔLES
# ==========================================
st.title("📊 Dashboard Performances Yassir")
st.markdown("---")

st.markdown("### ⚙️ Configuration & Données")
col_am, col_upload = st.columns([1, 2])

with col_am:
    am_choisi = st.selectbox("Pipeline", ["Houda", "Yassine", "Sara", "Amine"], label_visibility="collapsed")
    st.caption(f"📂 Config lue : `Pipeline - {am_choisi}.csv`")

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
    df_pipeline = pd.read_csv(f"Pipeline - {am_choisi}.csv", sep=None, engine='python')
    df_data = pd.read_csv(fichier_data)

    df_merged = pd.merge(df_data, df_pipeline, on="Restaurant ID", how="inner")
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
# 4. STRUCTURE DES ONGLETS (AJOUT DE L'AUTOMATION)
# ==========================================
tab_global, tab_pipeline, tab_flops, tab_annulations, tab_automation = st.tabs([
    "🌍 Analyse Global", 
    "📈 Overview Pipeline", 
    "🚨 Tops & Flops", 
    "❌ Annulations",
    "🤖 Automation"
])

# ----------------------------------------
# ONGLET 1 : ANALYSE GLOBAL
# ----------------------------------------
with tab_global:
    st.markdown("#### 🌍 Analyse Macro des Performances")
    
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
    
    st.markdown("##### 📈 Évolution du GMV")
    fig_macro = px.line(df_macro, x="Période", y="GMV", title="Tendance GMV", markers=True, template="plotly_white")
    st.plotly_chart(fig_macro, use_container_width=True)

# ----------------------------------------
# ONGLET 2 : OVERVIEW PIPELINE
# ----------------------------------------
with tab_pipeline:
    st.markdown(f"#### 📋 Tableau Détaillé ({semaine_selectionnee})")
    
    def compute_metrics(df_week):
        return df_week.groupby(['Area', 'Restaurant Name']).agg(
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
        
        df_compare = pd.merge(metrics_current, metrics_prev, on=['Area', 'Restaurant Name'], suffixes=('', '_prev'), how='left')
        
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
            df_compare[col.replace('wow ', '') + '_prev'] = 0 # Fallbacks for missing previous week

    colonnes_finales = [
        'Area', 'Restaurant Name', 'Semaine', 'Requested', 'Delivered', 'Success Rate', 
        'AcceptedByRestaurant', 'Taux Acceptation', 'CancelledByRestaurant', 'Taux Cancellation', 
        'GMV', 'AOV', 'Commission', 'Promo_Restaurant', 'Promo_Admin', 'LR_LG_Costs',
        'wow delivered', 'wow delivered %', 'wow T.A', 'wow Cancellation', 
        'wow GMV', 'Wow CA', 'Wow AOV', 'Wow Promo Order', 'Wow LR_LG_Costs'
    ]
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
# ONGLET 5 : AUTOMATION (NOUVEAU)
# ----------------------------------------
with tab_automation:
    st.markdown(f"#### 🤖 Suivi de l'Automatisation ({semaine_selectionnee})")
    st.markdown("Analyse de l'évolution du Taux d'Acceptation par les restaurants.")
    
    # --- TABLEAU 3 : RECAP GLOBAL ---
    st.markdown("##### 🌍 Récapitulatif Global")
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
    
    col_recap1.metric("Commandes Reçues (Requested)", f"{tot_req:,.0f}", f"{(tot_req - tot_req_prev):+,.0f} WoW")
    col_recap2.metric("Commandes Acceptées (Accepted)", f"{tot_acc:,.0f}", f"{(tot_acc - tot_acc_prev):+,.0f} WoW")
    col_recap3.metric("Taux d'Acceptation Global", f"{ta_global:.1%}", f"{wow_ta_global:+.1%} WoW")
    
    st.markdown("---")
    
    col_acc, col_reg = st.columns(2)
    cols_to_show = ['Restaurant Name', 'Area', 'Requested', 'Taux Acceptation_prev', 'Taux Acceptation', 'wow T.A']
    
    # --- TABLEAU 1 : ACCÉLÉRATION ---
    with col_acc:
        st.success("**🚀 Accélération (Top Progressions T.A)**")
        # On filtre ceux qui ont amélioré leur Taux (wow T.A > 0)
        df_acc = df_compare[df_compare['wow T.A'] > 0].sort_values('wow T.A', ascending=False).head(15)
        
        # Formatage propre
        df_acc_disp = df_acc[cols_to_show].copy()
        df_acc_disp['Taux Acceptation_prev'] = df_acc_disp['Taux Acceptation_prev'].apply(lambda x: f"{x:.1%}")
        df_acc_disp['Taux Acceptation'] = df_acc_disp['Taux Acceptation'].apply(lambda x: f"{x:.1%}")
        df_acc_disp['wow T.A'] = df_acc_disp['wow T.A'].apply(lambda x: f"{x:+.1%}")
        
        st.dataframe(df_acc_disp, hide_index=True, use_container_width=True)
        
        if not df_acc.empty:
            fig_acc = px.bar(df_acc.head(10), x="wow T.A", y="Restaurant Name", orientation='h', 
                             title="Top 10 - Accélérations", color_discrete_sequence=['#2ecc71'])
            fig_acc.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_acc, use_container_width=True)
        else:
            st.info("Aucune accélération constatée cette semaine.")

    # --- TABLEAU 2 : RÉGRESSION ---
    with col_reg:
        st.error("**⚠️ Régression (Pires Chutes T.A)**")
        # On filtre ceux qui ont chuté (wow T.A < 0)
        df_reg = df_compare[df_compare['wow T.A'] < 0].sort_values('wow T.A', ascending=True).head(15)
        
        # Formatage propre
        df_reg_disp = df_reg[cols_to_show].copy()
        df_reg_disp['Taux Acceptation_prev'] = df_reg_disp['Taux Acceptation_prev'].apply(lambda x: f"{x:.1%}")
        df_reg_disp['Taux Acceptation'] = df_reg_disp['Taux Acceptation'].apply(lambda x: f"{x:.1%}")
        df_reg_disp['wow T.A'] = df_reg_disp['wow T.A'].apply(lambda x: f"{x:+.1%}")
        
        st.dataframe(df_reg_disp, hide_index=True, use_container_width=True)
        
        if not df_reg.empty:
            fig_reg = px.bar(df_reg.head(10), x="wow T.A", y="Restaurant Name", orientation='h', 
                             title="Top 10 - Régressions", color_discrete_sequence=['#e74c3c'])
            fig_reg.update_layout(yaxis={'categoryorder':'total descending'})
            st.plotly_chart(fig_reg, use_container_width=True)
        else:
            st.info("Aucune régression constatée cette semaine.")
