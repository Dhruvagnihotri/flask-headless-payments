# Production Deployment Checklist

## ✅ Pre-Deployment

### Environment Configuration
- [ ] Set `STRIPE_API_KEY` (production key, not test)
- [ ] Set `STRIPE_WEBHOOK_SECRET` (from Stripe Dashboard)
- [ ] Set `SECRET_KEY` (strong, random value)
- [ ] Set `JWT_SECRET_KEY` (strong, random value)
- [ ] Set `SQLALCHEMY_DATABASE_URI` (production database)
- [ ] Configure `PAYMENTSVC_SUCCESS_URL` (production URL)
- [ ] Configure `PAYMENTSVC_CANCEL_URL` (production URL)
- [ ] Configure `PAYMENTSVC_RETURN_URL` (production URL)

### Stripe Configuration
- [ ] Create products in Stripe Dashboard
- [ ] Create prices for each plan
- [ ] Configure webhook endpoint in Stripe Dashboard
- [ ] Test webhook with Stripe CLI
- [ ] Enable required webhook events:
  - `checkout.session.completed`
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.payment_succeeded`
  - `invoice.payment_failed`

### Database
- [ ] Run database migrations
- [ ] Create database indexes
- [ ] Set up database backups
- [ ] Configure connection pooling
- [ ] Test database failover

### Security
- [ ] Enable HTTPS (SSL/TLS certificates)
- [ ] Configure CORS origins (no wildcards)
- [ ] Enable rate limiting
- [ ] Set up firewall rules
- [ ] Configure security headers
- [ ] Enable CSRF protection if using cookies
- [ ] Review and rotate all secrets

## 🔒 Security Hardening

### Application
- [ ] Disable debug mode (`DEBUG=False`)
- [ ] Use production WSGI server (Gunicorn/uWSGI)
- [ ] Configure proper logging (no sensitive data)
- [ ] Set up log rotation
- [ ] Enable request ID tracking
- [ ] Configure timeouts

### Monitoring
- [ ] Set up health check endpoints
- [ ] Configure uptime monitoring (e.g., UptimeRobot)
- [ ] Set up error tracking (e.g., Sentry)
- [ ] Configure metrics collection (e.g., Prometheus)
- [ ] Set up alerts for critical errors
- [ ] Monitor Stripe API rate limits
- [ ] Track subscription metrics

### Infrastructure
- [ ] Set up load balancer
- [ ] Configure auto-scaling
- [ ] Set up CDN for static assets
- [ ] Configure Redis for caching (optional)
- [ ] Set up background job queue (Celery/RQ)
- [ ] Configure backup and disaster recovery

## 📊 Testing

### Functional Testing
- [ ] Test all payment flows (checkout, upgrade, cancel)
- [ ] Test webhook delivery and processing
- [ ] Test subscription lifecycle
- [ ] Test error scenarios
- [ ] Test plan protection decorators
- [ ] Test idempotency

### Load Testing
- [ ] Perform load testing
- [ ] Test concurrent requests
- [ ] Test database connection pool
- [ ] Test Stripe API rate limits
- [ ] Test circuit breaker

### Integration Testing
- [ ] Test with production Stripe test mode
- [ ] Test frontend integration
- [ ] Test mobile app integration (if applicable)
- [ ] Test third-party integrations

## 🚀 Deployment

### Pre-Launch
- [ ] Create deployment runbook
- [ ] Set up rollback procedure
- [ ] Create incident response plan
- [ ] Train support team
- [ ] Prepare customer communication

### Launch
- [ ] Deploy to staging environment
- [ ] Run smoke tests
- [ ] Deploy to production
- [ ] Verify health checks
- [ ] Monitor error rates
- [ ] Monitor webhook processing
- [ ] Check subscription creation

### Post-Launch
- [ ] Monitor for 24 hours
- [ ] Check error logs
- [ ] Verify webhook processing
- [ ] Check subscription renewals
- [ ] Monitor customer feedback

## 🔄 Ongoing Maintenance

### Daily
- [ ] Check error rates
- [ ] Monitor webhook failures
- [ ] Check payment failures
- [ ] Review critical alerts

### Weekly
- [ ] Review subscription metrics
- [ ] Check failed payments
- [ ] Clean up old webhook events
- [ ] Clean up old idempotency keys
- [ ] Review security logs

### Monthly
- [ ] Update dependencies
- [ ] Review and optimize database
- [ ] Check for Stripe API updates
- [ ] Review pricing and plans
- [ ] Audit access logs

## 🆘 Incident Response

### Webhook Failures
1. Check Stripe webhook logs
2. Verify webhook secret
3. Check application logs
4. Manually process missed events if needed
5. Fix underlying issue
6. Monitor for recovery

### Payment Failures
1. Check Stripe Dashboard
2. Review customer's payment method
3. Contact customer if needed
4. Update payment method
5. Retry payment if appropriate

### Service Outage
1. Check health endpoints
2. Check database connectivity
3. Check Stripe API status
4. Enable circuit breaker if needed
5. Communicate with customers
6. Implement fix
7. Monitor recovery

## 📝 Documentation

- [ ] Update API documentation
- [ ] Document deployment process
- [ ] Create troubleshooting guide
- [ ] Document monitoring procedures
- [ ] Create customer support guide

## ⚡ Performance Optimization

- [ ] Enable database query caching
- [ ] Optimize slow queries
- [ ] Configure CDN caching
- [ ] Enable response compression
- [ ] Optimize webhook processing
- [ ] Consider async processing for heavy operations

## 🔐 Compliance

- [ ] Review PCI DSS requirements (if handling cards)
- [ ] Ensure GDPR compliance (if EU customers)
- [ ] Configure data retention policies
- [ ] Set up audit logging
- [ ] Document security practices

## ✅ Launch Criteria

Service is ready for production when:
- [ ] All environment variables configured
- [ ] All tests passing
- [ ] Health checks working
- [ ] Monitoring configured
- [ ] Webhooks processing successfully
- [ ] Error handling tested
- [ ] Rollback procedure documented
- [ ] Team trained
- [ ] Security review completed

---

**Remember: Start with Stripe test mode in production, then switch to live mode once everything is verified!**

