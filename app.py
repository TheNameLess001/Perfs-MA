# On ajoute le nouvel onglet "Analyse Global" en première position
tab_global, tab_pipeline, tab_flops, tab_annulations = st.tabs([
    "🌍 Analyse Global", 
    "📈 Overview Pipeline", 
    "🚨 Tops & Flops", 
    "❌ Annulations"
])

# ==========================================
# 🌍 ONGLET 1 : ANALYSE GLOBAL
# ==========================================
with tab_global:
    st.markdown("#### 🌍 Analyse Macro des Performances")
    
    # 1. Le sélecteur de vue (Jour / WoW / MoM) aligné horizontalement
    vue_temporelle = st.radio(
        "Sélectionnez la vue temporelle :",
        ["📅 Jour", "📊 Week over Week (WoW)", "📆 Month over Month (MoM)"],
        horizontal=True,
        label_visibility="collapsed" # Cache le titre pour un look plus épuré
    )
    
    st.markdown("---")
    
    # 2. Préparation du tableau (Ici, j'utilise des données fictives pour le design)
    # Dans la réalité, Pandas calculera ces chiffres automatiquement selon la "vue_temporelle" choisie
    data_macro = {
        "Période": ["Week 27", "Week 26", "Week 25"], # S'adaptera en "Jour" ou "Mois"
        "Reçu": [1500, 1420, 1300],
        "Livré": [1245, 1200, 1150],
        "GMV (MAD)": [125000, 118000, 110000],
        "CA (MAD)": [18750, 17700, 16500],
        "AOV (MAD)": [100.4, 98.3, 95.6],
        "V. Reçu": ["+5.6%", "+9.2%", "-"],
        "V. Livré": ["+3.7%", "+4.3%", "-"],
        "V. GMV": ["+5.9%", "+7.2%", "-"],
        "V. CA": ["+5.9%", "+7.2%", "-"],
        "V. AOV": ["+2.1%", "+2.8%", "-"]
    }
    df_global = pd.DataFrame(data_macro)
    
    # 3. Affichage du tableau
    st.dataframe(
        df_global,
        use_container_width=True,
        hide_index=True
    )
    
    st.info(f"💡 Affichage actuel : Vous regardez la vue **{vue_temporelle}**.")

# ==========================================
# 📈 ONGLET 2 : OVERVIEW PIPELINE
# ==========================================
with tab_pipeline:
    st.markdown(f"#### 📋 Tableau de Synthèse : {am_choisi}")
    # Le tableau Overview que nous avons créé précédemment viendra ici
    # st.dataframe(...)
