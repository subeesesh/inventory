export const ROLES = {
  owner: 'Store Owner',
  cashier: 'Cashier',
  inventory_manager: 'Inventory Manager',
  procurement_officer: 'Procurement Officer',
  finance_officer: 'Finance Officer',
};

// Who may open each screen (mirrors the backend's require_role guards)
export const ACCESS = {
  dashboard:  ['owner', 'inventory_manager', 'procurement_officer', 'finance_officer'],
  twin:       ['owner', 'inventory_manager', 'procurement_officer', 'finance_officer'],
  decisions:  ['owner', 'inventory_manager', 'procurement_officer', 'finance_officer'],
  simulator:  ['owner', 'inventory_manager', 'procurement_officer', 'finance_officer'],
  copilot:    ['owner', 'inventory_manager', 'procurement_officer', 'finance_officer'],
  monitoring: ['owner', 'inventory_manager', 'procurement_officer', 'finance_officer'],
  pos:        ['owner', 'cashier'],
  inventory:  ['owner', 'cashier', 'inventory_manager', 'procurement_officer'],
  purchases:  ['owner', 'procurement_officer', 'finance_officer'],
  customers:  ['owner', 'cashier', 'finance_officer'],
  compliance: ['owner', 'finance_officer'],
  settings:   ['owner', 'cashier', 'inventory_manager', 'procurement_officer', 'finance_officer'],
};

export const can = (role, area) => (ACCESS[area] || []).includes(role);

// Decision types each role is offered in the UI (the API itself accepts any analyst role)
export const TRIGGER_ROLES = {
  reorder_quantity:          ['owner', 'inventory_manager', 'procurement_officer'],
  price_adjustment:          ['owner', 'finance_officer'],
  promotion_trigger:         ['owner', 'inventory_manager'],
  staffing_adjustment:       ['owner', 'inventory_manager', 'finance_officer'],
  customer_retention_action: ['owner', 'inventory_manager'],
};

export const DECISION_TYPES = {
  reorder_quantity:          { label: 'Reorder quantity', tone: 'info',    axis: 'Units to order' },
  price_adjustment:          { label: 'Price adjustment', tone: 'violet',  axis: 'Price change ($)' },
  promotion_trigger:         { label: 'Promotion',        tone: 'warning', axis: 'Discount depth' },
  staffing_adjustment:       { label: 'Staffing',         tone: 'success', axis: 'Hours change' },
  customer_retention_action: { label: 'Retention',        tone: 'danger',  axis: 'Retention level' },
};

export const AGENT_LABELS = {
  inventory: 'Inventory',
  sales: 'Sales',
  finance: 'Finance',
  procurement: 'Procurement',
  pricing: 'Pricing',
  marketing: 'Marketing',
  hr: 'HR',
  customer_management: 'Customer',
  risk: 'Risk',
};

export const BUSINESS_GOALS = {
  maximize_profit:   { label: 'Maximise profit',   hint: 'Balance revenue and cost; the default for most stores.' },
  minimize_cost:     { label: 'Minimise cost',     hint: 'Favour smaller orders and lower spend.' },
  minimize_risk:     { label: 'Minimise risk',     hint: 'Adds the Risk agent as a modifier; avoids stock-outs and cash strain.' },
  maximize_turnover: { label: 'Maximise turnover', hint: 'Favour moving stock quickly, even at thinner margins.' },
};

export const SEVERITY_TONE = { critical: 'danger', warning: 'warning', info: 'info' };

export const ACTION_STATUS = {
  notified:       { tone: 'info',    label: 'Notified' },
  pending_review: { tone: 'warning', label: 'Needs review' },
  approved:       { tone: 'success', label: 'Approved' },
  rejected:       { tone: 'neutral', label: 'Rejected' },
};
