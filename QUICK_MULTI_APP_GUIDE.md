# ⚡ Quick Multi-App Setup Guide

## TL;DR

When running multiple apps on the same Flask instance, use **instance-level parameters** instead of shared config:

### ❌ OLD WAY (Causes Conflicts)

```python
# BAD: Config is shared, causes conflicts
app.config['AUTHSVC_URL_PREFIX'] = '/api/pdfwhiz/auth'
pdfwhiz_auth = AuthSvc(app, user_model=PdfwhizUser)

app.config['AUTHSVC_URL_PREFIX'] = '/api/whogoes/auth'  # Overwrites!
whogoes_auth = AuthSvc(app, user_model=WhoGoesUser)
```

### ✅ NEW WAY (No Conflicts)

```python
# GOOD: Each instance has its own configuration
pdfwhiz_auth = AuthSvc(
    app,
    user_model=PdfwhizUser,
    url_prefix='/api/pdfwhiz/auth',      # ✅ Instance-level
    blueprint_name='pdfwhiz_auth'        # ✅ Unique name
)

pdfwhiz_payments = PaymentSvc(
    app,
    user_model=PdfwhizUser,
    url_prefix='/api/pdfwhiz/payments',  # ✅ Instance-level
    blueprint_name='pdfwhiz_payments',   # ✅ Unique name
    plans={'pdf_pro': {...}}
)

whogoes_auth = AuthSvc(
    app,
    user_model=WhoGoesUser,
    url_prefix='/api/whogoes/auth',      # ✅ Different prefix
    blueprint_name='whogoes_auth'        # ✅ Unique name
)

whogoes_payments = PaymentSvc(
    app,
    user_model=WhoGoesUser,
    url_prefix='/api/whogoes/payments',  # ✅ Different prefix
    blueprint_name='whogoes_payments',   # ✅ Unique name
    plans={'whogoes_premium': {...}}
)
```

---

## 📊 Result

```
Routes registered:
├─ /api/pdfwhiz/auth/*
├─ /api/pdfwhiz/payments/*
├─ /api/whogoes/auth/*
└─ /api/whogoes/payments/*

Blueprints:
├─ pdfwhiz_auth
├─ pdfwhiz_payments
├─ whogoes_auth
└─ whogoes_payments

✅ No conflicts!
```

---

## 🔑 Key Rules

1. **Always specify `url_prefix`** when using multiple instances
2. **Always specify `blueprint_name`** when using multiple instances
3. **Don't rely on `app.config`** for multi-app setups
4. **Each blueprint name must be unique** across the entire Flask app

---

## 📚 Full Documentation

- **MULTI_APP_SETUP.md** - Detailed patterns and examples
- **MULTI_APP_ARCHITECTURE.md** - Visual diagrams and architecture
- **ARCHITECTURE.md** - General package architecture

---

**That's it! Your multi-app setup is ready.** 🚀

