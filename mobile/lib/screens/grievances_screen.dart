import 'package:flutter/material.dart';

import '../api_client.dart';
import '../models.dart';

class GrievancesScreen extends StatefulWidget {
  const GrievancesScreen({super.key});

  @override
  State<GrievancesScreen> createState() => _GrievancesScreenState();
}

class _GrievancesScreenState extends State<GrievancesScreen> {
  final SahayakApi _api = SahayakApi();
  List<Grievance> _grievances = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await _api.listGrievances();
      if (!mounted) return;
      setState(() {
        _grievances = list;
        _loading = false;
      });
    } on Exception catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'Failed to load grievances: $e';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('My grievances  •  मेरी शिकायतें'),
        centerTitle: true,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? _errorView(scheme)
              : _grievances.isEmpty
                  ? _emptyView(scheme)
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView.builder(
                        physics: const AlwaysScrollableScrollPhysics(),
                        padding: const EdgeInsets.all(12),
                        itemCount: _grievances.length,
                        itemBuilder: (context, i) => _card(_grievances[i], scheme),
                      ),
                    ),
    );
  }

  Widget _errorView(ColorScheme scheme) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: 48, color: scheme.error),
            const SizedBox(height: 12),
            Text(_error!, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton(onPressed: _load, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }

  Widget _emptyView(ColorScheme scheme) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.inbox_outlined, size: 56, color: scheme.onSurfaceVariant),
          const SizedBox(height: 12),
          const Text('No grievances filed yet.'),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: () => Navigator.of(context).pushNamed('/conversation'),
            icon: const Icon(Icons.mic_rounded),
            label: const Text('File a grievance'),
          ),
        ],
      ),
    );
  }

  Widget _card(Grievance g, ColorScheme scheme) {
    final statusColor = switch (g.status) {
      'overdue' => scheme.error,
      'escalated' => const Color(0xFFB00020),
      'resolved' => const Color(0xFF2E7D32),
      _ => scheme.primary,
    };
    final statusLabel = switch (g.status) {
      'overdue' => 'Overdue by ${g.overdueDays}d',
      'escalated' => 'Escalated',
      'resolved' => 'Resolved',
      _ => 'In progress',
    };
    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 10),
      color: g.isOverdue
          ? scheme.errorContainer.withValues(alpha: 0.35)
          : scheme.surfaceContainerHighest,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: g.isOverdue ? () => _appealDialog(g) : null,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      g.ministry,
                      style: Theme.of(context)
                          .textTheme
                          .titleSmall
                          ?.copyWith(fontWeight: FontWeight.bold),
                    ),
                  ),
                  Chip(
                    label: Text(statusLabel),
                    labelStyle: TextStyle(
                      color: statusColor,
                      fontWeight: FontWeight.w600,
                      fontSize: 11,
                    ),
                    backgroundColor: statusColor.withValues(alpha: 0.12),
                    visualDensity: VisualDensity.compact,
                    padding: EdgeInsets.zero,
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                g.description,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: 8),
              Text(
                'ID: ${g.registrationId}',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
              ),
              const SizedBox(height: 2),
              Text(
                'SLA deadline: ${_fmtDate(g.deadline)}',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
              ),
              if (g.isOverdue) ...[
                const SizedBox(height: 10),
                Row(
                  children: [
                    Icon(Icons.gavel_rounded, size: 16, color: scheme.error),
                    const SizedBox(width: 6),
                    Text(
                      'Tap to draft the appeal',
                      style: TextStyle(color: scheme.error, fontSize: 12),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _appealDialog(Grievance g) async {
    final draft = g.appealDraft ??
        'A formal appeal for ${g.registrationId} has been drafted. '
        'It references the original complaint and its SLA deadline.';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Draft appeal  •  अपील ड्राफ्ट'),
        content: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('This grievance is past its deadline. Sahayak drafted '
                  'a formal second-level appeal. Shall we file it?'),
              const SizedBox(height: 12),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  draft,
                  style: const TextStyle(fontSize: 12, height: 1.4),
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('No'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('File appeal'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    if (!mounted) return;
    try {
      await _api.escalateGrievance(g.registrationId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Appeal filed. Sahayak will notify you of the outcome.'),
        ),
      );
      await _load();
    } on Exception catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Escalation failed: $e')),
      );
    }
  }

  String _fmtDate(String iso) {
    if (iso.isEmpty) return '—';
    return iso.substring(0, 10);
  }
}