<script>
  import { onMount } from 'svelte';
  import { api } from './api';
  import funStars from './assets/fun-stars.svg';
  import choreRocket from './assets/chore-rocket.svg';
  import rewardCastle from './assets/reward-castle.svg';

  let loading = true;
  let user = null;
  let error = '';
  let activeTab = 'dashboard';

  let chores = [];
  let rewards = [];
  let redemptions = [];
  let ledger = [];
  let ledgerTotal = 0;
  let pendingChores = [];
  let users = [];
  let children = [];
  let selectedLedgerUser = '';

  let loginUsername = '';
  let loginPassword = '';

  let newChore = {
    title: '',
    description: '',
    points: 10,
    recurrence: 'NONE',
    due_date: '',
    assignee_ids: []
  };

  let newReward = {
    name: '',
    cost: 25,
    limit_per_week: ''
  };

  async function bootstrap() {
    loading = true;
    error = '';
    try {
      user = await api('/api/me');
      await loadData();
    } catch {
      user = null;
    } finally {
      loading = false;
    }
  }

  async function refreshLedger() {
    if (!user) return;

    if (user.role === 'CHILD') {
      const ledgerData = await api('/api/ledger');
      ledger = ledgerData.entries;
      ledgerTotal = ledgerData.total;
      return;
    }

    if (!selectedLedgerUser && children.length > 0) {
      selectedLedgerUser = String(children[0].id);
    }

    if (!selectedLedgerUser) {
      ledger = [];
      ledgerTotal = 0;
      return;
    }

    const ledgerData = await api(`/api/ledger?user_id=${selectedLedgerUser}`);
    ledger = ledgerData.entries;
    ledgerTotal = ledgerData.total;
  }

  async function loadData() {
    if (!user) return;
    error = '';
    try {
      [chores, rewards, redemptions] = await Promise.all([
        api('/api/chores'),
        api('/api/rewards'),
        api('/api/redemptions')
      ]);

      if (user.role === 'ADMIN') {
        users = await api('/api/users');
      }

      if (user.role === 'ADMIN' || user.role === 'PARENT') {
        children = await api('/api/children');
        pendingChores = await api('/api/chores?status=DONE_PENDING');
      }

      await refreshLedger();
    } catch (e) {
      error = e.message;
    }
  }

  async function login() {
    error = '';
    try {
      await api('/api/login', {
        method: 'POST',
        body: JSON.stringify({ username: loginUsername, password: loginPassword })
      });
      loginPassword = '';
      await bootstrap();
    } catch (e) {
      error = e.message;
    }
  }

  async function logout() {
    await api('/api/logout', { method: 'POST' });
    user = null;
    chores = [];
    rewards = [];
    redemptions = [];
    ledger = [];
    pendingChores = [];
    users = [];
    children = [];
    selectedLedgerUser = '';
  }

  async function createChore() {
    try {
      await api('/api/chores', {
        method: 'POST',
        body: JSON.stringify(newChore)
      });
      newChore = { title: '', description: '', points: 10, recurrence: 'NONE', due_date: '', assignee_ids: [] };
      await loadData();
    } catch (e) {
      error = e.message;
    }
  }

  async function createReward() {
    try {
      await api('/api/rewards', {
        method: 'POST',
        body: JSON.stringify({
          name: newReward.name,
          cost: newReward.cost,
          is_active: true,
          limit_per_week: newReward.limit_per_week === '' ? null : Number(newReward.limit_per_week)
        })
      });
      newReward = { name: '', cost: 25, limit_per_week: '' };
      await loadData();
    } catch (e) {
      error = e.message;
    }
  }

  async function markDone(choreId) {
    await api(`/api/chores/${choreId}/done`, { method: 'POST' });
    await loadData();
  }

  async function approveChore(choreId) {
    await api(`/api/chores/${choreId}/approve`, { method: 'POST', body: JSON.stringify({ note: 'Approved' }) });
    await loadData();
  }

  async function rejectChore(choreId) {
    await api(`/api/chores/${choreId}/reject`, { method: 'POST', body: JSON.stringify({ note: 'Try again' }) });
    await loadData();
  }

  async function redeemReward(rewardId) {
    await api(`/api/rewards/${rewardId}/redeem`, { method: 'POST' });
    await loadData();
  }

  async function approveRedemption(redemptionId) {
    await api(`/api/redemptions/${redemptionId}/approve`, { method: 'POST', body: JSON.stringify({ note: 'Approved' }) });
    await loadData();
  }

  async function denyRedemption(redemptionId) {
    await api(`/api/redemptions/${redemptionId}/deny`, { method: 'POST', body: JSON.stringify({ note: 'Denied' }) });
    await loadData();
  }

  function toggleAssignee(id) {
    if (newChore.assignee_ids.includes(id)) {
      newChore.assignee_ids = newChore.assignee_ids.filter((x) => x !== id);
      return;
    }
    newChore.assignee_ids = [...newChore.assignee_ids, id];
  }

  onMount(bootstrap);
</script>

<div class="scene-bg" aria-hidden="true">
  <div class="blob one"></div>
  <div class="blob two"></div>
  <div class="blob three"></div>
</div>

{#if loading}
  <main class="shell"><p>Loading...</p></main>
{:else if !user}
  <main class="shell auth">
    <img class="hero sticker-float" src={funStars} alt="Kid friendly stars graphic" />
    <h1>HR for Kids</h1>
    <p class="subtitle">Team up, finish chores, unlock cool rewards.</p>
    <form on:submit|preventDefault={login}>
      <label>Username <input bind:value={loginUsername} required /></label>
      <label>Password <input type="password" bind:value={loginPassword} required /></label>
      <button type="submit">Launch Mission</button>
    </form>
    {#if error}<p class="error">{error}</p>{/if}
  </main>
{:else}
  <main class="shell">
    <header>
      <div>
        <h1>HR for Kids</h1>
        <p class="subtitle">{user.display_name} ({user.role})</p>
      </div>
      <div class="actions">
        <button on:click={loadData}>Refresh</button>
        <button on:click={logout}>Logout</button>
      </div>
    </header>

    <nav class="tabs">
      <button class:active={activeTab === 'dashboard'} on:click={() => (activeTab = 'dashboard')}>Dashboard</button>
      <button class:active={activeTab === 'chores'} on:click={() => (activeTab = 'chores')}>Chores</button>
      <button class:active={activeTab === 'rewards'} on:click={() => (activeTab = 'rewards')}>Rewards</button>
      {#if user.role !== 'CHILD'}
        <button class:active={activeTab === 'approvals'} on:click={() => (activeTab = 'approvals')}>Approvals</button>
      {/if}
      {#if user.role === 'ADMIN'}
        <button class:active={activeTab === 'users'} on:click={() => (activeTab = 'users')}>Users</button>
      {/if}
    </nav>

    {#if error}<p class="error">{error}</p>{/if}

    {#if activeTab === 'dashboard'}
      <section class="card highlight">
        <div class="visual-row">
          <div>
            <h2>Points</h2>
            <p class="metric">{ledgerTotal}</p>
          </div>
          <img class="mini-graphic sticker-float" src={funStars} alt="Stars" />
        </div>
      </section>

      {#if user.role !== 'CHILD'}
      <section class="card">
        <h2>View Child Ledger</h2>
        <select bind:value={selectedLedgerUser} on:change={refreshLedger}>
          {#each children as child}
            <option value={String(child.id)}>{child.display_name}</option>
          {/each}
        </select>
      </section>
      {/if}

      <section class="card">
        <h2>Ledger (latest)</h2>
        <ul>
          {#each ledger.slice(0, 10) as entry}
            <li>{entry.created_at.slice(0, 10)}: {entry.delta} ({entry.reason})</li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if activeTab === 'chores'}
      {#if user.role !== 'CHILD'}
      <section class="card">
        <h2>Create Chore</h2>
        <form class="grid" on:submit|preventDefault={createChore}>
          <input placeholder="Title" bind:value={newChore.title} required />
          <input placeholder="Description" bind:value={newChore.description} />
          <input type="number" min="0" bind:value={newChore.points} required />
          <select bind:value={newChore.recurrence}>
            <option value="NONE">NONE</option>
            <option value="DAILY">DAILY</option>
            <option value="WEEKLY">WEEKLY</option>
          </select>
          <input type="date" bind:value={newChore.due_date} />
          <fieldset>
            <legend>Assign to</legend>
            {#each children as c}
              <label>
                <input type="checkbox" checked={newChore.assignee_ids.includes(c.id)} on:change={() => toggleAssignee(c.id)} />
                {c.display_name}
              </label>
            {/each}
          </fieldset>
          <button type="submit">Create</button>
        </form>
      </section>
      {/if}

      <section class="card">
        <div class="visual-row">
          <h2>Chores</h2>
          <img class="mini-graphic sticker-bounce" src={choreRocket} alt="Rocket graphic for chores" />
        </div>
        <table>
          <thead><tr><th>Title</th><th>Status</th><th>Due</th><th>Points</th><th></th></tr></thead>
          <tbody>
          {#each chores as c}
            <tr>
              <td>{c.title}</td>
              <td>{c.status}</td>
              <td>{c.due_date || '-'}</td>
              <td>{c.points}</td>
              <td>
                {#if user.role === 'CHILD' && (c.status === 'ASSIGNED' || c.status === 'REJECTED')}
                  <button on:click={() => markDone(c.id)}>Mark Done</button>
                {/if}
              </td>
            </tr>
          {/each}
          </tbody>
        </table>
      </section>
    {/if}

    {#if activeTab === 'rewards'}
      {#if user.role !== 'CHILD'}
      <section class="card">
        <h2>Create Reward</h2>
        <form class="grid" on:submit|preventDefault={createReward}>
          <input placeholder="Name" bind:value={newReward.name} required />
          <input type="number" min="0" bind:value={newReward.cost} required />
          <input type="number" min="1" placeholder="Limit per week" bind:value={newReward.limit_per_week} />
          <button type="submit">Create</button>
        </form>
      </section>
      {/if}

      <section class="card">
        <div class="visual-row">
          <h2>Rewards</h2>
          <img class="mini-graphic sticker-float" src={rewardCastle} alt="Castle graphic for rewards" />
        </div>
        <table>
          <thead><tr><th>Name</th><th>Cost</th><th></th></tr></thead>
          <tbody>
          {#each rewards as r}
            <tr>
              <td>{r.name}</td>
              <td>{r.cost}</td>
              <td>
                {#if user.role === 'CHILD'}
                  <button on:click={() => redeemReward(r.id)}>Redeem</button>
                {/if}
              </td>
            </tr>
          {/each}
          </tbody>
        </table>
      </section>

      <section class="card">
        <h2>Redemptions</h2>
        <table>
          <thead><tr><th>Reward</th><th>User</th><th>Status</th><th></th></tr></thead>
          <tbody>
          {#each redemptions as rd}
            <tr>
              <td>{rd.reward_name}</td>
              <td>{rd.user_name}</td>
              <td>{rd.status}</td>
              <td>
                {#if user.role !== 'CHILD' && rd.status === 'REQUESTED'}
                  <button on:click={() => approveRedemption(rd.id)}>Approve</button>
                  <button class="muted" on:click={() => denyRedemption(rd.id)}>Deny</button>
                {/if}
              </td>
            </tr>
          {/each}
          </tbody>
        </table>
      </section>
    {/if}

    {#if activeTab === 'approvals' && user.role !== 'CHILD'}
      <section class="card">
        <h2>Pending Chores</h2>
        <table>
          <thead><tr><th>Title</th><th>Points</th><th>Status</th><th></th></tr></thead>
          <tbody>
          {#each pendingChores as c}
            <tr>
              <td>{c.title}</td>
              <td>{c.points}</td>
              <td>{c.status}</td>
              <td>
                <button on:click={() => approveChore(c.id)}>Approve</button>
                <button class="muted" on:click={() => rejectChore(c.id)}>Reject</button>
              </td>
            </tr>
          {/each}
          </tbody>
        </table>
      </section>
    {/if}

    {#if activeTab === 'users' && user.role === 'ADMIN'}
      <section class="card">
        <h2>Users</h2>
        <table>
          <thead><tr><th>Username</th><th>Name</th><th>Role</th><th>Active</th></tr></thead>
          <tbody>
          {#each users as u}
            <tr>
              <td>{u.username}</td>
              <td>{u.display_name}</td>
              <td>{u.role}</td>
              <td>{u.is_active ? 'yes' : 'no'}</td>
            </tr>
          {/each}
          </tbody>
        </table>
      </section>
    {/if}
  </main>
{/if}

<style>
  :global(body) {
    margin: 0;
    font-family: 'Comic Sans MS', 'Trebuchet MS', 'Segoe UI', sans-serif;
    background: radial-gradient(circle at 20% 20%, #ffe2a8, #ffd3c7 35%, #c9edff 70%, #a9dbff 100%);
    color: #1a2a3e;
    min-height: 100vh;
  }
  .scene-bg {
    position: fixed;
    inset: 0;
    z-index: -1;
    overflow: hidden;
    pointer-events: none;
  }
  .blob {
    position: absolute;
    border-radius: 50%;
    filter: blur(2px);
    opacity: 0.5;
  }
  .blob.one { width: 320px; height: 320px; left: -90px; top: -60px; background: #ffd166; }
  .blob.two { width: 360px; height: 360px; right: -110px; top: 80px; background: #7edca2; }
  .blob.three { width: 280px; height: 280px; left: 35%; bottom: -120px; background: #82c7ff; }

  .shell {
    max-width: 1080px;
    margin: 0 auto;
    padding: 24px;
  }
  .auth {
    max-width: 450px;
    margin-top: 32px;
    background: rgba(255, 255, 255, 0.75);
    border-radius: 20px;
    backdrop-filter: blur(6px);
    box-shadow: 0 18px 32px rgba(17, 46, 77, 0.18);
  }
  .subtitle {
    margin-top: -8px;
    color: #3c5875;
    font-weight: 700;
  }
  .hero {
    width: 100%;
    border-radius: 16px;
    margin-bottom: 12px;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: rgba(255, 255, 255, 0.75);
    border-radius: 16px;
    padding: 12px 16px;
    box-shadow: 0 10px 26px rgba(17, 46, 77, 0.12);
  }
  .tabs {
    display: flex;
    gap: 8px;
    margin: 16px 0;
    flex-wrap: wrap;
  }
  .tabs button {
    background: #ff9f43;
    color: #1a2a3e;
    font-weight: 700;
  }
  .tabs button.active {
    background: #1366d6;
    color: #fff;
  }
  .card {
    background: rgba(255, 255, 255, 0.85);
    border-radius: 16px;
    padding: 16px;
    margin: 12px 0;
    box-shadow: 0 12px 26px rgba(20, 46, 72, 0.14);
    border: 2px solid rgba(255, 255, 255, 0.5);
  }
  .highlight {
    background: linear-gradient(135deg, rgba(255,255,255,0.95), rgba(255, 248, 224, 0.95));
  }
  .visual-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .mini-graphic {
    width: 90px;
    height: 90px;
    object-fit: contain;
  }
  .grid {
    display: grid;
    gap: 10px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    border-radius: 12px;
    overflow: hidden;
  }
  th {
    background: #e8f5ff;
    color: #24486f;
  }
  th, td {
    text-align: left;
    border-bottom: 1px solid #dbe9f8;
    padding: 8px;
    font-size: 14px;
  }
  fieldset {
    border: 1px solid #bdd5f0;
    border-radius: 8px;
    padding: 8px;
    background: #f7fbff;
  }
  .metric {
    font-size: 44px;
    line-height: 1;
    font-weight: 900;
    margin: 0;
    color: #1366d6;
  }
  .error {
    color: #a51515;
    background: #ffe9e9;
    padding: 10px 12px;
    border-radius: 10px;
    font-weight: 700;
  }
  .actions {
    display: flex;
    gap: 8px;
  }
  .sticker-float {
    animation: floaty 3s ease-in-out infinite;
  }
  .sticker-bounce {
    animation: bouncy 1.8s ease-in-out infinite;
  }
  button {
    border: 0;
    background: #1f7aeb;
    color: white;
    padding: 8px 12px;
    border-radius: 10px;
    cursor: pointer;
    font-weight: 700;
  }
  button.muted {
    background: #6a8bab;
  }
  input, select {
    width: 100%;
    box-sizing: border-box;
    padding: 8px;
    border: 1px solid #a8c9ea;
    border-radius: 10px;
    background: #fff;
  }
  @media (max-width: 720px) {
    .shell { padding: 12px; }
    th, td { font-size: 12px; }
    .mini-graphic { width: 64px; height: 64px; }
    header { flex-direction: column; align-items: flex-start; gap: 8px; }
  }
  @keyframes floaty {
    0% { transform: translateY(0px); }
    50% { transform: translateY(-8px); }
    100% { transform: translateY(0px); }
  }
  @keyframes bouncy {
    0% { transform: translateY(0) scale(1); }
    30% { transform: translateY(-10px) scale(1.03); }
    60% { transform: translateY(0) scale(0.98); }
    100% { transform: translateY(0) scale(1); }
  }
</style>
