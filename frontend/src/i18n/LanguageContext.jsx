import { createContext, useContext, useEffect, useMemo, useState } from "react";

const LANGUAGE_STORAGE_KEY = "smart-spending-language";

export const SUPPORTED_LANGUAGES = {
  en: {
    code: "en",
    shortLabel: "EN",
    label: "English",
  },
  fr: {
    code: "fr",
    shortLabel: "FR",
    label: "Français",
  },
};

const translations = {
  en: {
    common: {
      appName: "Smart Spending Analyzer",
      assistant: "Assistant",
      backToDashboard: "Back to Dashboard",
      dashboard: "Dashboard",
      smartImport: "Smart Import",
      moneyMap: "Money Map",
      transactions: "Transactions",
      analytics: "Analytics",
      analyticsInsights: "Analytics & Insights",
      budgets: "Budgets",
      simulator: "Simulator",
      futureSimulator: "Future Simulator",
      accounts: "Accounts",
      profileSettings: "Profile & Settings",
      viewPremium: "View Premium",
      openPage: "Open a page",
      appMenu: "App Menu",
      logout: "Logout",
      backToTransactions: "Back to Transactions",
      reviewTransactions: "Review Transactions",
      account: "Account",
      accountScope: "Account scope",
      allAccounts: "All Accounts",
      loadingAccounts: "Loading accounts...",
      income: "Income",
      expense: "Expense",
      expenses: "Expenses",
      balance: "Balance",
      category: "Category",
      description: "Description",
      amount: "Amount",
      date: "Date",
      type: "Type",
      all: "All",
      month: "Month",
      from: "From",
      to: "To",
      clearFilters: "Clear Filters",
      loadingPage: "Loading page...",
      loadingPageDetail: "Preparing the next screen for you.",
      premium: "Premium",
      uploadStatement: "Upload Statement",
      viewAnalytics: "View Analytics",
      viewLedger: "View Ledger",
      assistantPage: "Assistant",
      targetAccount: "Target Account",
    },
    language: {
      label: "Language",
      switchToFrench: "Passer en français",
      switchToEnglish: "Switch to English",
    },
    theme: {
      toggle: "Toggle theme",
      dark: "Dark",
      light: "Light",
      switchToDark: "Switch to dark mode",
      switchToLight: "Switch to light mode",
    },
    auth: {
      explore: "Explore",
      chooseWhereToStart: "Choose where to start",
      createFreeAccount: "Create free account",
      loginFailed: "Login failed. Please check your email and password.",
      passwordMismatch: "Passwords do not match.",
      registrationFailed: "Registration failed. Email may already be in use.",
      forgotFailed: "Failed to send reset instructions.",
      resetFailed: "Failed to reset password.",
      heroTitle: "Understand your money with a cleaner, smarter workflow.",
      heroDescription:
        "Write daily transactions, reconcile bank statements at month-end, and let the app learn your categories, recurring habits, and future money outlook.",
      monthEndTitle: "Month-end reconciliation",
      monthEndDetail: "Compare what you wrote daily against your real bank statement.",
      categoryMemoryTitle: "Learned category memory",
      categoryMemoryDetail:
        "Teach the app your personal naming habits instead of accepting generic guesses.",
      premiumTitle: "Premium planning cockpit",
      premiumDetail:
        "Advanced forecasts, larger statement batches, saved scenarios, and guided spending plans.",
      premiumPreview: "Premium preview",
      premiumPreviewDetail:
        "Unlock deeper 3 and 6 month analysis, bigger import batches, simulator portfolios, and smarter recurring-charge decisions when plans launch.",
      startFree: "Start free, upgrade later",
      welcomeBack: "Welcome back",
      login: "Login",
      loginDetail: "Sign in to access your dashboard, analytics, and assistant.",
      email: "Email",
      emailPlaceholder: "Enter your email",
      password: "Password",
      passwordPlaceholder: "Enter your password",
      forgotPassword: "Forgot password?",
      noAccount: "Don't have an account?",
      createOne: "Create one",
      registerHeroTitle: "Build a better view of your spending from day one.",
      registerHeroDetail:
        "Create your account to import transactions, explore analytics, and use intelligent guidance designed around your financial behavior.",
      simpleOnboarding: "Simple onboarding",
      simpleOnboardingDetail: "Start with manual entries or import your existing records.",
      actionableAnalytics: "Actionable analytics",
      actionableAnalyticsDetail: "See what changed, what dominates spending, and where to improve.",
      guidedExploration: "Assistant-guided exploration",
      guidedExplorationDetail: "Ask questions and move naturally through your data.",
      getStarted: "Get started",
      createAccount: "Create account",
      createAccountDetail: "Set up your account and start using the full platform.",
      createPassword: "Create a password",
      confirmPassword: "Confirm Password",
      confirmPasswordPlaceholder: "Confirm your password",
      createAccountButton: "Create Account",
      alreadyHaveAccount: "Already have an account?",
      accountRecovery: "Account recovery",
      forgotPasswordTitle: "Forgot password",
      forgotPasswordDetail: "Enter your email and we'll generate a password reset link.",
      generating: "Generating...",
      sendResetLink: "Send Reset Link",
      testResetLink: "Test reset link:",
      openResetPage: "Open password reset page",
      backTo: "Back to",
      resetPasswordTitle: "Reset password",
      resetPasswordDetail: "Create a new password for your account.",
      missingResetToken: "Missing reset token.",
      passwordResetSuccess: "Password reset successfully.",
      newPassword: "New Password",
      newPasswordPlaceholder: "Enter your new password",
      confirmNewPassword: "Confirm New Password",
      confirmNewPasswordPlaceholder: "Confirm your new password",
      resetting: "Resetting...",
      resetPasswordButton: "Reset Password",
    },
    headers: {
      dashboardSubtitle:
        "Your current-month command center. Start here each day, record what happened, and jump into deeper tools only when you need them.",
      transactionsSubtitle:
        "Your ledger is the source of truth. Write daily transactions here, then reconcile the bank statement at month-end to catch what you forgot.",
      analyticsSubtitle:
        "Learn what changed, what is driving your spending, and whether your recent pace is getting better or worse.",
      importSubtitle:
        "Use daily transactions as your source of truth, then upload the month-end statement to find what you missed.",
      accountsSubtitle:
        "Create separate accounts and switch between combined and account-specific views.",
      budgetsSubtitle:
        "Plan category limits by month and see how your real spending is tracking against them.",
      moneyMapEyebrow: "Smart Money Twin",
      moneyMapSubtitle:
        "Upload real statements and this page becomes your learned spending model: categories, recurring bills, confidence, and next best actions.",
      simulatorSubtitle:
        "Test future balances, monthly changes, and saved scenarios before the month surprises you.",
      assistantSubtitle:
        "Ask questions about your accounts, categories, budget pace, and future outlook.",
      profileSubtitle:
        "Manage account settings, premium plans, and your personal app preferences.",
    },
    dashboard: {
      loadingTitle: "Loading dashboard...",
      loadingDetail: "Please wait while your financial overview is being prepared.",
      howTitle: "How to use this dashboard",
      howDetail:
        "This page is intentionally simple: it shows this month only, helps you add today's transaction, and gives you a quick future warning before you go deeper.",
      chooseViewTitle: "Choose your view",
      chooseViewDetail:
        "Use Account View to see all accounts together or focus on one account when you only want one bank card, chequing account, or cash account.",
      writeDailyTitle: "Write daily transactions",
      writeDailyDetail:
        "Add expenses and income when they happen. At month-end, Smart Import compares your bank statement against this written history and helps find anything you missed.",
      watchMonthTitle: "Watch the month",
      watchMonthDetail:
        "The overview and Future Outlook tell you whether the current month is healthy. For detailed charts, open Analytics instead of crowding the dashboard.",
      accountView: "Account View",
      accountViewDetail: "Switch between all accounts combined or one specific account.",
      dayZero: "Day-0 setup",
      moneyMapTitle: "Build your Money Map from one statement",
      moneyMapDetail:
        "Instead of staring at zero charts, upload a bank statement and let the app learn categories, recurring bills, and simulator assumptions from real activity.",
      openMoneyMap: "Open Money Map",
      overview: "Overview",
      overviewDetail:
        "A simple current-month snapshot. For daily, weekly, monthly, 3-month, and 6-month analysis, open Analytics.",
      incomeNote: "Income recorded this month",
      expenseNote: "Expenses recorded this month",
      balanceNote: "Current-month net",
      openDetailedAnalytics: "Open Detailed Analytics",
      futureOutlook: "Future Outlook",
      futureOutlookDetail: "A quick 3-month projection for the current account scope.",
      startingBalance: "Starting Balance",
      monthlyNet: "Monthly Net",
      threeMonthImpact: "3-Month Impact",
      projectedBalance: "Projected Balance",
      openFullSimulator: "Open Full Simulator",
      premiumEyebrow: "Premium planning layer",
      premiumTitle: "Turn your spending history into a financial operating system.",
      premiumDetail:
        "Premium is where advanced forecasting, larger statement batches, category learning history, custom money rules, and guided monthly plans will live. Free stays clean and useful; Premium becomes the cockpit for people who want smarter decisions every month.",
      statementBatch: "6+ statement batch import",
      trendPacks: "3 and 6 month trend packs",
      simulatorScenarios: "Advanced simulator scenarios",
      categoryControls: "Category learning controls",
      seePlans: "See Plans",
      previewSimulator: "Preview Simulator",
      budgetHealth: "Budget Health",
      budgetHealthDetail: "Quick budget status for {month} in the current scope.",
      noBudgets: "No budgets are set for this month yet.",
      createBudgets: "Create Budgets",
    },
    transactions: {
      loadingTitle: "Loading transactions...",
      loadingDetail: "Please wait while your transaction history is being prepared.",
      reconcileStatement: "Reconcile Statement",
      howTitle: "How transactions work",
      howDetail:
        "Think of this page as your financial notebook. The more consistently you write here, the smarter the app becomes at spotting habits, repeated payments, and category patterns.",
      daily: "Daily",
      dailyTitle: "Record what you remember",
      dailyDetail:
        "Add purchases, bills, income, and transfers as they happen. These are the transactions you personally confirmed.",
      month: "Month",
      monthTitle: "Reconcile the statement",
      monthDetail:
        "Upload the month-end bank statement from Smart Import. The app looks for matching written rows and only offers the missing statement rows for import.",
      learn: "Learn",
      learnTitle: "Improve category memory",
      learnDetail:
        "Normalize categories and review suggestions when needed. Your naming habits help the app suggest cleaner categories next time.",
      accountViewDetail: "Select all accounts or focus on one account.",
      freshStart: "Fresh Start",
      freshStartDetail:
        "Remove old statement history and keep the transactions from your new spending life. This is built for your new workflow: write daily transactions, then reconcile the month-end bank statement.",
      keepFrom: "Keep transactions from",
      deleteOldHistory: "Delete Old History",
      cleaning: "Cleaning...",
      reconcileThisMonth: "Reconcile This Month",
      repeatingPatterns: "Repeating Money Patterns",
      repeatingPatternsDetail:
        "Repeated expenses and income detected from your written transaction history in this scope.",
      smartCategorization: "Smart Categorization",
      smartCategorizationDetail:
        "Analyze uncategorized rows and clean up legacy category labels so future suggestions stay consistent.",
      transactionFilters: "Transaction Filters",
      transactionTable: "Transaction Table",
      addToday: "Add Today's Transaction",
      noTransactions: "No transactions found in this account view yet.",
    },
    analytics: {
      howTitle: "How to read Analytics",
      howDetail:
        "Analytics is the deeper learning page. Use the quick ranges first, then read the pattern chart to see whether spending is rising, dropping, or staying stable.",
      shortTermPace: "Short-term pace",
      shortTermDetail:
        "Last 7 Days shows the newest spending pulse. Use it when you want to know if this week is heavier than normal.",
      currentMonthControl: "Current month control",
      currentMonthDetail:
        "Current Month keeps the view focused on the month you are living in right now, which is the best range for budgeting decisions.",
      longerDirection: "Longer-term direction",
      longerDirectionDetail:
        "Last 3 Months catches recent behavior changes. Last 6 Months shows the bigger baseline so you can tell whether the change is real or just one odd month.",
      filtersTitle: "Analytics Filters",
      filtersDetail: "Refine the analysis using account scope, month, date range, type, and category.",
      last7Days: "Last 7 Days",
      currentMonth: "Current Month",
      last3Months: "Last 3 Months",
      last6Months: "Last 6 Months",
      totalIncome: "Total Income",
      totalExpenses: "Total Expenses",
      topExpenseCategory: "Top Expense Category",
      noExpenseData: "No expense data",
      spendingPulse: "Spending Pattern Pulse",
      spendingPulseDetail:
        "Dot-and-line view of your expense movement. It compares this week against the current month, then recent 3-month behavior against the 6-month baseline.",
    },
    import: {
      destination: "Import Destination",
      destinationDetail: "Select the account where imported transactions should go.",
      uploadFiles: "Upload Files",
      uploadFilesDetail:
        "Upload up to {limit} CSV or PDF bank statements in one try. The app marks rows already written and lets you import only the missed transactions.",
      selectStatement:
        "Select this month's statement to reconcile your daily entries. More than {limit} files in one batch is a Premium workflow.",
      chooseFiles: "Choose Files",
      processing: "Processing...",
      selectedFiles: "Selected files:",
      noFiles: "No files selected yet",
      processingUpload: "Processing upload...",
      processingDetail: "Detecting each file type and running the correct import pipeline.",
      importFailed: "Import failed",
      dismiss: "Dismiss",
      completed: "Import completed",
      clear: "Clear",
      imported: "Imported",
      duplicatesSkipped: "Duplicates skipped",
      invalidRowsSkipped: "Invalid rows skipped",
    },
    moneyMap: {
      loadingTitle: "Building Money Map...",
      loadingDetail: "Reading your learned patterns and financial signals.",
      scopeTitle: "Money Map Scope",
      scopeDetail: "Switch between all accounts or one account-specific learned model.",
      lowConfidence: "Low confidence",
      modelConfidence: "model confidence",
      startStatement: "Start with one statement",
      learnedModel: "Your learned financial model",
      dayZero: "The day-0 hook",
      dayZeroTitle: "Upload one bank statement. Get a Money Map in under a minute.",
      dayZeroDetail:
        "Banks show transactions. This app should learn what those transactions mean: your merchant habits, your category language, recurring leaks, and simulator-ready assumptions.",
      importStatement: "Import statement",
      importStatementDetail: "PDF or CSV becomes reviewed transactions.",
      teachCategories: "Teach categories",
      teachCategoriesDetail: "Corrections train your merchant and slang memory.",
      unlockPlanning: "Unlock planning",
      unlockPlanningDetail: "Budgets and simulator stop being empty.",
      learnedMerchants: "Learned Merchants",
      learningSignals: "Learning Signals",
      learningSignalsDetail: "How much the Money Map trusts the current data.",
    },
    budgets: {
      scopeTitle: "Budget Scope",
      scopeAll: "These budgets apply across all accounts combined.",
      scopeOne: "These budgets apply only to the selected account.",
      scopeLabel: "Budget scope",
      rolloverNote:
        "Reuse the previous month for a straight rollover, or build {nextMonth} from {month}'s live pace when you want smarter targets. Existing budgets in the target month stay untouched.",
      copying: "Copying...",
      building: "Building...",
      copyBudgets: "Copy {month} Budgets",
      buildFromPace: "Build {month} From Pace",
    },
    assistant: {
      title: "Financial Assistant",
      modeTitle: "Assistant mode",
      modeDetail: "Choose how you want the assistant to respond.",
      modeLabel: "Personality mode",
      balanced: "Balanced",
      strict: "Strict",
      coach: "Coach",
      currentMode: "Current mode:",
      currentScope: "Current scope:",
      strictDescription: "Direct and accountability-focused.",
      coachDescription: "Supportive and motivating.",
      balancedDescription: "Neutral and practical.",
      scopeTitle: "Assistant scope",
      scopeDetail: "Choose whether answers should use all accounts combined or one specific account.",
      scopeLabel: "Assistant scope",
      scopeAll: "All accounts combined.",
      scopeOne: "Focused on the selected account only.",
      smartPrompts: "Smart prompts",
      promptsLoading: "Loading finance-aware prompts...",
      promptsReady:
        "These prompts are generated from your current financial data in the selected scope.",
    },
    simulator: {
      scenarioControls: "Scenario Controls",
      scopeAll: "Projection uses all accounts combined.",
      scopeOne: "Projection uses only the selected account.",
      copyScenarioLink: "Copy Scenario Link",
      recommendedPlans: "Recommended Plans",
      recommendedPlansDetail:
        "Backend-ranked simulator ideas based on recurring costs, cash-flow pressure, and current budget risk.",
    },
    profile: {
      loadingTitle: "Loading profile...",
      loadingDetail: "Please wait while your account settings are being prepared.",
      eyebrow: "Account Settings",
      title: "Profile",
      subtitle: "Manage your account details, security settings, and account access.",
      infoTitle: "Profile Information",
      infoDetail: "Update the email address linked to your account.",
      emailAddress: "Email address",
      saveProfile: "Save Profile",
      changePassword: "Change Password",
      changePasswordDetail: "Update your password to keep your account secure.",
      currentPassword: "Current Password",
      currentPasswordPlaceholder: "Enter your current password",
      newPassword: "New Password",
      newPasswordPlaceholder: "Enter your new password",
    },
    accounts: {
      createAccount: "Create Account",
      createAccountDetail: "Add a new financial account for tracking.",
      accountName: "Account name",
      chequing: "Chequing",
      savings: "Savings",
      creditCard: "Credit Card",
      cash: "Cash",
      business: "Business",
      other: "Other",
      yourAccounts: "Your Accounts",
      noAccounts: "No accounts found.",
      review: "Review",
      delete: "Delete",
      createFailed: "Failed to create account.",
      deleteFailed: "Failed to delete account.",
    },
    transactionForm: {
      editTitle: "Edit Transaction",
      addTitle: "Add Transaction",
      suggestCategory: "Suggest Category",
      suggesting: "Suggesting...",
      update: "Update Transaction",
      add: "Add Transaction",
      cancel: "Cancel",
      suggestedCategory: "Suggested Category",
      confidence: "Confidence",
      matchedKeyword: "Matched keyword",
      descriptionRequired: "Please enter a description before requesting a category suggestion.",
      suggestFailed: "Failed to suggest a category.",
      updateFailed: "Failed to update transaction.",
      createFailed: "Failed to create transaction.",
    },
  },
  fr: {
    common: {
      appName: "Analyseur intelligent des dépenses",
      assistant: "Assistant",
      backToDashboard: "Retour au tableau de bord",
      dashboard: "Tableau de bord",
      smartImport: "Importation intelligente",
      moneyMap: "Carte financière",
      transactions: "Transactions",
      analytics: "Analyses",
      analyticsInsights: "Analyses et informations",
      budgets: "Budgets",
      simulator: "Simulateur",
      futureSimulator: "Simulateur financier",
      accounts: "Comptes",
      profileSettings: "Profil et paramètres",
      viewPremium: "Voir Premium",
      openPage: "Ouvrir une page",
      appMenu: "Menu de l'application",
      logout: "Déconnexion",
      backToTransactions: "Retour aux transactions",
      reviewTransactions: "Voir les transactions",
      account: "Compte",
      accountScope: "Portée du compte",
      allAccounts: "Tous les comptes",
      loadingAccounts: "Chargement des comptes...",
      income: "Revenus",
      expense: "Dépense",
      expenses: "Dépenses",
      balance: "Solde",
      category: "Catégorie",
      description: "Description",
      amount: "Montant",
      date: "Date",
      type: "Type",
      all: "Tout",
      month: "Mois",
      from: "De",
      to: "À",
      clearFilters: "Effacer les filtres",
      loadingPage: "Chargement de la page...",
      loadingPageDetail: "Préparation du prochain écran.",
      premium: "Premium",
      uploadStatement: "Importer un relevé",
      viewAnalytics: "Voir les analyses",
      viewLedger: "Voir le registre",
      assistantPage: "Assistant",
      targetAccount: "Compte cible",
    },
    language: {
      label: "Langue",
      switchToFrench: "Passer en français",
      switchToEnglish: "Switch to English",
    },
    theme: {
      toggle: "Changer le thème",
      dark: "Sombre",
      light: "Clair",
      switchToDark: "Passer au mode sombre",
      switchToLight: "Passer au mode clair",
    },
    auth: {
      explore: "Explorer",
      chooseWhereToStart: "Choisir où commencer",
      createFreeAccount: "Créer un compte gratuit",
      loginFailed: "Connexion échouée. Vérifiez votre courriel et votre mot de passe.",
      passwordMismatch: "Les mots de passe ne correspondent pas.",
      registrationFailed: "Inscription échouée. Ce courriel est peut-être déjà utilisé.",
      forgotFailed: "Impossible d'envoyer les instructions de réinitialisation.",
      resetFailed: "Impossible de réinitialiser le mot de passe.",
      heroTitle: "Comprenez votre argent avec un flux plus clair et plus intelligent.",
      heroDescription:
        "Notez vos transactions quotidiennes, rapprochez vos relevés bancaires à la fin du mois et laissez l'application apprendre vos catégories, vos habitudes récurrentes et votre projection financière.",
      monthEndTitle: "Rapprochement de fin de mois",
      monthEndDetail: "Comparez ce que vous avez noté chaque jour avec votre vrai relevé bancaire.",
      categoryMemoryTitle: "Mémoire de catégories",
      categoryMemoryDetail:
        "Apprenez à l'application vos propres habitudes de nommage au lieu d'accepter des suppositions génériques.",
      premiumTitle: "Poste de pilotage Premium",
      premiumDetail:
        "Prévisions avancées, lots de relevés plus grands, scénarios sauvegardés et plans de dépenses guidés.",
      premiumPreview: "Aperçu Premium",
      premiumPreviewDetail:
        "Débloquez l'analyse sur 3 et 6 mois, de plus gros lots d'importation, des portefeuilles de scénarios et de meilleures décisions sur les charges récurrentes lorsque les forfaits seront lancés.",
      startFree: "Commencer gratuitement, améliorer plus tard",
      welcomeBack: "Bon retour",
      login: "Connexion",
      loginDetail: "Connectez-vous pour accéder à votre tableau de bord, vos analyses et votre assistant.",
      email: "Courriel",
      emailPlaceholder: "Entrez votre courriel",
      password: "Mot de passe",
      passwordPlaceholder: "Entrez votre mot de passe",
      forgotPassword: "Mot de passe oublié?",
      noAccount: "Vous n'avez pas de compte?",
      createOne: "Créez-en un",
      registerHeroTitle: "Construisez une meilleure vue de vos dépenses dès le premier jour.",
      registerHeroDetail:
        "Créez votre compte pour importer des transactions, explorer les analyses et utiliser des conseils intelligents adaptés à votre comportement financier.",
      simpleOnboarding: "Démarrage simple",
      simpleOnboardingDetail: "Commencez avec des entrées manuelles ou importez vos relevés existants.",
      actionableAnalytics: "Analyses utiles",
      actionableAnalyticsDetail: "Voyez ce qui a changé, ce qui domine vos dépenses et où vous améliorer.",
      guidedExploration: "Exploration guidée par l'assistant",
      guidedExplorationDetail: "Posez des questions et naviguez naturellement dans vos données.",
      getStarted: "Commencer",
      createAccount: "Créer un compte",
      createAccountDetail: "Configurez votre compte et commencez à utiliser la plateforme complète.",
      createPassword: "Créer un mot de passe",
      confirmPassword: "Confirmer le mot de passe",
      confirmPasswordPlaceholder: "Confirmez votre mot de passe",
      createAccountButton: "Créer le compte",
      alreadyHaveAccount: "Vous avez déjà un compte?",
      accountRecovery: "Récupération du compte",
      forgotPasswordTitle: "Mot de passe oublié",
      forgotPasswordDetail: "Entrez votre courriel et nous générerons un lien de réinitialisation.",
      generating: "Génération...",
      sendResetLink: "Envoyer le lien",
      testResetLink: "Lien de test:",
      openResetPage: "Ouvrir la page de réinitialisation",
      backTo: "Retour à",
      resetPasswordTitle: "Réinitialiser le mot de passe",
      resetPasswordDetail: "Créez un nouveau mot de passe pour votre compte.",
      missingResetToken: "Jeton de réinitialisation manquant.",
      passwordResetSuccess: "Mot de passe réinitialisé avec succès.",
      newPassword: "Nouveau mot de passe",
      newPasswordPlaceholder: "Entrez votre nouveau mot de passe",
      confirmNewPassword: "Confirmer le nouveau mot de passe",
      confirmNewPasswordPlaceholder: "Confirmez votre nouveau mot de passe",
      resetting: "Réinitialisation...",
      resetPasswordButton: "Réinitialiser le mot de passe",
    },
    headers: {
      dashboardSubtitle:
        "Votre centre de contrôle du mois en cours. Commencez ici chaque jour, notez ce qui s'est passé et ouvrez les outils avancés seulement au besoin.",
      transactionsSubtitle:
        "Votre registre est la source de vérité. Notez les transactions au quotidien, puis rapprochez le relevé bancaire à la fin du mois pour trouver les oublis.",
      analyticsSubtitle:
        "Comprenez ce qui a changé, ce qui influence vos dépenses et si votre rythme récent s'améliore ou se détériore.",
      importSubtitle:
        "Utilisez vos transactions quotidiennes comme source de vérité, puis importez le relevé de fin de mois pour trouver ce qui manque.",
      accountsSubtitle:
        "Créez des comptes séparés et basculez entre une vue combinée et une vue par compte.",
      budgetsSubtitle:
        "Planifiez des limites par catégorie et par mois, puis suivez vos dépenses réelles.",
      moneyMapEyebrow: "Jumeau financier intelligent",
      moneyMapSubtitle:
        "Importez de vrais relevés et cette page devient votre modèle de dépenses appris: catégories, factures récurrentes, confiance et prochaines actions.",
      simulatorSubtitle:
        "Testez les soldes futurs, les changements mensuels et les scénarios sauvegardés avant que le mois vous surprenne.",
      assistantSubtitle:
        "Posez des questions sur vos comptes, catégories, rythme budgétaire et perspectives financières.",
      profileSubtitle:
        "Gérez les paramètres du compte, les forfaits Premium et vos préférences d'application.",
    },
    dashboard: {
      loadingTitle: "Chargement du tableau de bord...",
      loadingDetail: "Veuillez patienter pendant la préparation de votre aperçu financier.",
      howTitle: "Comment utiliser ce tableau de bord",
      howDetail:
        "Cette page reste volontairement simple: elle montre seulement le mois en cours, vous aide à ajouter la transaction du jour et donne un avertissement rapide sur l'avenir.",
      chooseViewTitle: "Choisir votre vue",
      chooseViewDetail:
        "Utilisez la vue Compte pour voir tous les comptes ensemble ou concentrez-vous sur une seule carte, un compte chèques ou un compte en espèces.",
      writeDailyTitle: "Noter les transactions quotidiennes",
      writeDailyDetail:
        "Ajoutez les dépenses et les revenus quand ils arrivent. En fin de mois, l'importation intelligente compare votre relevé bancaire avec cet historique et aide à trouver les oublis.",
      watchMonthTitle: "Surveiller le mois",
      watchMonthDetail:
        "L'aperçu et la projection future indiquent si le mois en cours est sain. Pour les graphiques détaillés, ouvrez plutôt Analyses.",
      accountView: "Vue du compte",
      accountViewDetail: "Basculez entre tous les comptes combinés ou un compte précis.",
      dayZero: "Démarrage jour 0",
      moneyMapTitle: "Construisez votre Carte financière à partir d'un relevé",
      moneyMapDetail:
        "Au lieu de regarder des graphiques vides, importez un relevé bancaire et laissez l'application apprendre les catégories, les factures récurrentes et les hypothèses du simulateur.",
      openMoneyMap: "Ouvrir la Carte financière",
      overview: "Aperçu",
      overviewDetail:
        "Un aperçu simple du mois en cours. Pour les analyses quotidiennes, hebdomadaires, mensuelles, sur 3 mois et sur 6 mois, ouvrez Analyses.",
      incomeNote: "Revenus enregistrés ce mois-ci",
      expenseNote: "Dépenses enregistrées ce mois-ci",
      balanceNote: "Solde net du mois en cours",
      openDetailedAnalytics: "Ouvrir les analyses détaillées",
      futureOutlook: "Projection future",
      futureOutlookDetail: "Une projection rapide sur 3 mois pour la portée actuelle.",
      startingBalance: "Solde de départ",
      monthlyNet: "Net mensuel",
      threeMonthImpact: "Impact sur 3 mois",
      projectedBalance: "Solde projeté",
      openFullSimulator: "Ouvrir le simulateur complet",
      premiumEyebrow: "Couche de planification Premium",
      premiumTitle: "Transformez votre historique de dépenses en système d'exploitation financier.",
      premiumDetail:
        "Premium regroupera les prévisions avancées, les gros lots de relevés, l'historique d'apprentissage des catégories, les règles personnalisées et les plans mensuels guidés.",
      statementBatch: "Importation de lots de 6+ relevés",
      trendPacks: "Tendances sur 3 et 6 mois",
      simulatorScenarios: "Scénarios avancés du simulateur",
      categoryControls: "Contrôles d'apprentissage des catégories",
      seePlans: "Voir les forfaits",
      previewSimulator: "Prévisualiser le simulateur",
      budgetHealth: "Santé du budget",
      budgetHealthDetail: "Statut rapide du budget pour {month} dans la portée actuelle.",
      noBudgets: "Aucun budget n'est défini pour ce mois.",
      createBudgets: "Créer des budgets",
    },
    transactions: {
      loadingTitle: "Chargement des transactions...",
      loadingDetail: "Veuillez patienter pendant la préparation de votre historique.",
      reconcileStatement: "Rapprocher le relevé",
      howTitle: "Comment fonctionnent les transactions",
      howDetail:
        "Considérez cette page comme votre carnet financier. Plus vous écrivez régulièrement ici, plus l'application détecte les habitudes, paiements répétés et catégories.",
      daily: "Quotidien",
      dailyTitle: "Noter ce dont vous vous souvenez",
      dailyDetail:
        "Ajoutez les achats, factures, revenus et transferts quand ils arrivent. Ce sont les transactions que vous avez confirmées.",
      month: "Mois",
      monthTitle: "Rapprocher le relevé",
      monthDetail:
        "Importez le relevé bancaire de fin de mois. L'application cherche les lignes déjà écrites et propose seulement les transactions manquantes.",
      learn: "Apprendre",
      learnTitle: "Améliorer la mémoire des catégories",
      learnDetail:
        "Normalisez les catégories et révisez les suggestions au besoin. Vos habitudes de nommage aident l'application à mieux suggérer la prochaine fois.",
      accountViewDetail: "Sélectionnez tous les comptes ou concentrez-vous sur un compte.",
      freshStart: "Nouveau départ",
      freshStartDetail:
        "Supprimez l'ancien historique de relevés et gardez les transactions de votre nouvelle vie financière: écrivez chaque jour, puis rapprochez le relevé mensuel.",
      keepFrom: "Conserver les transactions à partir du",
      deleteOldHistory: "Supprimer l'ancien historique",
      cleaning: "Nettoyage...",
      reconcileThisMonth: "Rapprocher ce mois-ci",
      repeatingPatterns: "Habitudes d'argent récurrentes",
      repeatingPatternsDetail:
        "Dépenses et revenus répétés détectés à partir de votre historique écrit dans cette portée.",
      smartCategorization: "Catégorisation intelligente",
      smartCategorizationDetail:
        "Analysez les lignes non catégorisées et nettoyez les anciennes étiquettes pour garder les futures suggestions cohérentes.",
      transactionFilters: "Filtres de transactions",
      transactionTable: "Tableau des transactions",
      addToday: "Ajouter la transaction du jour",
      noTransactions: "Aucune transaction trouvée dans cette vue de compte.",
    },
    analytics: {
      howTitle: "Comment lire les analyses",
      howDetail:
        "Les analyses sont la page d'apprentissage approfondi. Utilisez d'abord les périodes rapides, puis lisez le graphique des tendances.",
      shortTermPace: "Rythme à court terme",
      shortTermDetail:
        "Les 7 derniers jours montrent le pouls récent des dépenses. Utilisez-les pour voir si cette semaine est plus lourde que d'habitude.",
      currentMonthControl: "Contrôle du mois courant",
      currentMonthDetail:
        "Le mois courant garde la vue concentrée sur le mois que vous vivez maintenant, idéal pour les décisions de budget.",
      longerDirection: "Direction à plus long terme",
      longerDirectionDetail:
        "Les 3 derniers mois captent les changements récents. Les 6 derniers mois montrent la base plus large.",
      filtersTitle: "Filtres d'analyse",
      filtersDetail: "Affinez l'analyse par compte, mois, dates, type et catégorie.",
      last7Days: "7 derniers jours",
      currentMonth: "Mois courant",
      last3Months: "3 derniers mois",
      last6Months: "6 derniers mois",
      totalIncome: "Revenus totaux",
      totalExpenses: "Dépenses totales",
      topExpenseCategory: "Principale catégorie de dépense",
      noExpenseData: "Aucune donnée de dépense",
      spendingPulse: "Pouls des habitudes de dépenses",
      spendingPulseDetail:
        "Vue avec points et lignes du mouvement de vos dépenses. Elle compare la semaine au mois courant, puis 3 mois récents à la base de 6 mois.",
    },
    import: {
      destination: "Destination de l'importation",
      destinationDetail: "Sélectionnez le compte où les transactions importées doivent aller.",
      uploadFiles: "Importer des fichiers",
      uploadFilesDetail:
        "Importez jusqu'à {limit} relevés bancaires CSV ou PDF en une fois. L'application marque les lignes déjà écrites et vous laisse importer seulement les transactions manquées.",
      selectStatement:
        "Sélectionnez le relevé de ce mois pour rapprocher vos entrées quotidiennes. Plus de {limit} fichiers par lot est un flux Premium.",
      chooseFiles: "Choisir les fichiers",
      processing: "Traitement...",
      selectedFiles: "Fichiers sélectionnés:",
      noFiles: "Aucun fichier sélectionné",
      processingUpload: "Traitement de l'importation...",
      processingDetail: "Détection du type de fichier et lancement du bon pipeline.",
      importFailed: "Échec de l'importation",
      dismiss: "Fermer",
      completed: "Importation terminée",
      clear: "Effacer",
      imported: "Importées",
      duplicatesSkipped: "Doublons ignorés",
      invalidRowsSkipped: "Lignes invalides ignorées",
    },
    moneyMap: {
      loadingTitle: "Construction de la Carte financière...",
      loadingDetail: "Lecture de vos habitudes apprises et signaux financiers.",
      scopeTitle: "Portée de la Carte financière",
      scopeDetail: "Basculez entre tous les comptes ou un modèle appris par compte.",
      lowConfidence: "Faible confiance",
      modelConfidence: "confiance du modèle",
      startStatement: "Commencer avec un relevé",
      learnedModel: "Votre modèle financier appris",
      dayZero: "Accroche jour 0",
      dayZeroTitle: "Importez un relevé bancaire. Obtenez une Carte financière en moins d'une minute.",
      dayZeroDetail:
        "Les banques montrent des transactions. Cette app apprend ce qu'elles signifient: vos marchands, votre langage de catégories, vos fuites récurrentes et les hypothèses du simulateur.",
      importStatement: "Importer un relevé",
      importStatementDetail: "Un PDF ou CSV devient des transactions révisées.",
      teachCategories: "Enseigner les catégories",
      teachCategoriesDetail: "Vos corrections entraînent la mémoire des marchands et des surnoms.",
      unlockPlanning: "Débloquer la planification",
      unlockPlanningDetail: "Les budgets et le simulateur cessent d'être vides.",
      learnedMerchants: "Marchands appris",
      learningSignals: "Signaux d'apprentissage",
      learningSignalsDetail: "Niveau de confiance de la Carte financière dans les données actuelles.",
    },
    budgets: {
      scopeTitle: "Portée du budget",
      scopeAll: "Ces budgets s'appliquent à tous les comptes combinés.",
      scopeOne: "Ces budgets s'appliquent seulement au compte sélectionné.",
      scopeLabel: "Portée du budget",
      rolloverNote:
        "Réutilisez le mois précédent pour un roulement simple, ou créez {nextMonth} à partir du rythme réel de {month} pour des cibles plus intelligentes. Les budgets existants dans le mois cible restent intacts.",
      copying: "Copie...",
      building: "Création...",
      copyBudgets: "Copier les budgets de {month}",
      buildFromPace: "Créer {month} depuis le rythme",
    },
    assistant: {
      title: "Assistant financier",
      modeTitle: "Mode de l'assistant",
      modeDetail: "Choisissez comment l'assistant doit répondre.",
      modeLabel: "Mode de personnalité",
      balanced: "Équilibré",
      strict: "Strict",
      coach: "Coach",
      currentMode: "Mode actuel:",
      currentScope: "Portée actuelle:",
      strictDescription: "Direct et axé sur la responsabilité.",
      coachDescription: "Encourageant et motivant.",
      balancedDescription: "Neutre et pratique.",
      scopeTitle: "Portée de l'assistant",
      scopeDetail: "Choisissez si les réponses utilisent tous les comptes ou un compte précis.",
      scopeLabel: "Portée de l'assistant",
      scopeAll: "Tous les comptes combinés.",
      scopeOne: "Centré sur le compte sélectionné seulement.",
      smartPrompts: "Questions intelligentes",
      promptsLoading: "Chargement des questions financières...",
      promptsReady:
        "Ces questions sont générées à partir de vos données financières dans la portée sélectionnée.",
    },
    simulator: {
      scenarioControls: "Contrôles du scénario",
      scopeAll: "La projection utilise tous les comptes combinés.",
      scopeOne: "La projection utilise seulement le compte sélectionné.",
      copyScenarioLink: "Copier le lien du scénario",
      recommendedPlans: "Plans recommandés",
      recommendedPlansDetail:
        "Idées classées par le backend selon les coûts récurrents, la pression de trésorerie et le risque budgétaire actuel.",
    },
    profile: {
      loadingTitle: "Chargement du profil...",
      loadingDetail: "Préparation des paramètres de votre compte.",
      eyebrow: "Paramètres du compte",
      title: "Profil",
      subtitle: "Gérez vos détails de compte, la sécurité et l'accès.",
      infoTitle: "Informations du profil",
      infoDetail: "Mettez à jour le courriel lié à votre compte.",
      emailAddress: "Adresse courriel",
      saveProfile: "Enregistrer le profil",
      changePassword: "Changer le mot de passe",
      changePasswordDetail: "Mettez à jour votre mot de passe pour garder le compte sécurisé.",
      currentPassword: "Mot de passe actuel",
      currentPasswordPlaceholder: "Entrez votre mot de passe actuel",
      newPassword: "Nouveau mot de passe",
      newPasswordPlaceholder: "Entrez votre nouveau mot de passe",
    },
    accounts: {
      createAccount: "Créer un compte",
      createAccountDetail: "Ajoutez un nouveau compte financier pour le suivi.",
      accountName: "Nom du compte",
      chequing: "Chèques",
      savings: "Épargne",
      creditCard: "Carte de crédit",
      cash: "Espèces",
      business: "Entreprise",
      other: "Autre",
      yourAccounts: "Vos comptes",
      noAccounts: "Aucun compte trouvé.",
      review: "Voir",
      delete: "Supprimer",
      createFailed: "Impossible de créer le compte.",
      deleteFailed: "Impossible de supprimer le compte.",
    },
    transactionForm: {
      editTitle: "Modifier la transaction",
      addTitle: "Ajouter une transaction",
      suggestCategory: "Suggérer une catégorie",
      suggesting: "Suggestion...",
      update: "Mettre à jour",
      add: "Ajouter la transaction",
      cancel: "Annuler",
      suggestedCategory: "Catégorie suggérée",
      confidence: "Confiance",
      matchedKeyword: "Mot-clé trouvé",
      descriptionRequired: "Entrez une description avant de demander une suggestion.",
      suggestFailed: "Impossible de suggérer une catégorie.",
      updateFailed: "Impossible de mettre à jour la transaction.",
      createFailed: "Impossible de créer la transaction.",
    },
  },
};

function readInitialLanguage() {
  const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
  if (stored && SUPPORTED_LANGUAGES[stored]) {
    return stored;
  }

  const browserLanguage = navigator.language?.toLowerCase() || "";
  return browserLanguage.startsWith("fr") ? "fr" : "en";
}

function resolveTranslation(language, key) {
  const keys = key.split(".");
  let current = translations[language];

  for (const part of keys) {
    current = current?.[part];
    if (current === undefined) {
      return undefined;
    }
  }

  return current;
}

function interpolate(value, params = {}) {
  if (typeof value !== "string") {
    return value;
  }

  return Object.entries(params).reduce(
    (current, [key, replacement]) => current.replaceAll(`{${key}}`, replacement),
    value
  );
}

const LanguageContext = createContext(null);

export function LanguageProvider({ children }) {
  const [language, setLanguage] = useState(readInitialLanguage);

  useEffect(() => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    document.documentElement.lang = language === "fr" ? "fr-CA" : "en-CA";
  }, [language]);

  const value = useMemo(() => {
    const t = (key, params) => {
      const translated = resolveTranslation(language, key) ?? resolveTranslation("en", key) ?? key;
      return interpolate(translated, params);
    };

    return {
      language,
      setLanguage,
      toggleLanguage: () => setLanguage((current) => (current === "fr" ? "en" : "fr")),
      isFrench: language === "fr",
      t,
    };
  }, [language]);

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  const context = useContext(LanguageContext);

  if (!context) {
    throw new Error("useLanguage must be used inside LanguageProvider");
  }

  return context;
}
