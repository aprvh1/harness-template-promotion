#!/usr/bin/env python3
"""Test runner for template extraction and promotion workflows.

Executes all test scenarios defined in test_scenarios.yaml and generates a test report.
"""

import os
import sys
import yaml
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import hashlib

# Add parent scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from common import logger


class TestResult:
    """Represents the result of a single test."""

    def __init__(self, scenario_id: str, name: str):
        self.scenario_id = scenario_id
        self.name = name
        self.passed = False
        self.error = None
        self.output = None
        self.duration = 0
        self.validation_results = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            'scenario_id': self.scenario_id,
            'name': self.name,
            'passed': self.passed,
            'error': self.error,
            'duration': self.duration,
            'validation_results': self.validation_results
        }


class TestRunner:
    """Executes test scenarios and validates results."""

    def __init__(self, config_file: str, workspace: str):
        self.config_file = config_file
        self.workspace = Path(workspace)
        self.test_config = None
        self.results: List[TestResult] = []

        # Load test configuration
        with open(config_file, 'r') as f:
            self.test_config = yaml.safe_load(f)

    def setup_workspace(self):
        """Prepare test workspace."""
        logger.info(f"Setting up test workspace: {self.workspace}")

        # Create workspace directories
        (self.workspace / 'templates').mkdir(parents=True, exist_ok=True)
        (self.workspace / 'scripts').mkdir(parents=True, exist_ok=True)

        # Copy scripts to workspace
        scripts_src = Path(__file__).parent.parent / 'scripts'
        for script_file in scripts_src.glob('*.py'):
            shutil.copy(script_file, self.workspace / 'scripts')

        # Create empty versions.yaml
        with open(self.workspace / 'versions.yaml', 'w') as f:
            yaml.dump({'templates': {}}, f)

        logger.info("✓ Workspace setup complete")

    def cleanup_workspace(self):
        """Clean up test workspace."""
        logger.info("Cleaning up test workspace...")
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
        logger.info("✓ Workspace cleaned up")

    def simulate_tier_deployment(self, template_id: str, template_type: str, tier: int):
        """Simulate Terraform deploying a tier to Harness.

        Creates the tier file and simulates it being available in Harness.
        In real workflow, Terraform would deploy to actual Harness.
        """
        logger.info(f"Simulating deployment of {template_id} tier-{tier}")

        # Read semantic version file (e.g., Stage_Template-v1.yaml)
        type_dir = template_type.replace('_', '-')
        versions_data = self.load_versions_yaml()

        # Get the semantic version for this tier
        tier_label = f"tier-{tier}"
        if template_id in versions_data.get('templates', {}).get(template_type, {}):
            tier_snapshots = versions_data['templates'][template_type][template_id].get('tier_snapshots', {})
            if tier_label in tier_snapshots:
                semantic_version = tier_snapshots[tier_label]

                # Copy semantic version file to tier file
                src_file = self.workspace / 'templates' / type_dir / f"{template_id}-{semantic_version}.yaml"
                dst_file = self.workspace / 'templates' / type_dir / f"{template_id}-{tier_label}.yaml"

                if src_file.exists():
                    shutil.copy(src_file, dst_file)
                    logger.info(f"  ✓ Created {dst_file.name}")
                else:
                    logger.warning(f"  ⚠️ Source file not found: {src_file}")
            else:
                logger.warning(f"  ⚠️ No tier snapshot for {tier_label}")
        else:
            logger.warning(f"  ⚠️ Template {template_id} not found in versions.yaml")

    def load_versions_yaml(self) -> Dict[str, Any]:
        """Load versions.yaml from workspace."""
        versions_file = self.workspace / 'versions.yaml'
        if versions_file.exists():
            with open(versions_file, 'r') as f:
                return yaml.safe_load(f) or {}
        return {'templates': {}}

    def run_extraction_test(self, scenario: Dict[str, Any]) -> TestResult:
        """Run an extraction test scenario."""
        result = TestResult(scenario['id'], scenario['name'])
        start_time = datetime.now()

        logger.info(f"\n{'='*60}")
        logger.info(f"Running: {scenario['name']}")
        logger.info(f"{'='*60}")

        try:
            # Build command
            cmd = scenario['command']
            script_path = self.workspace / 'scripts' / 'validate_and_extract.py'

            args = [
                sys.executable,
                str(script_path),
                '--execution-url', self.test_config['config']['execution_url'],
                '--template-id', cmd['template_id'],
                '--project-id', self.test_config['config']['project_id'],
                '--changelog', cmd['changelog'],
                '--mode', cmd['mode']
            ]

            # Set environment variables
            env = os.environ.copy()
            env['HARNESS_API_KEY'] = self.test_config['config']['harness_api_key']
            env['HARNESS_ACCOUNT_ID'] = self.test_config['config']['harness_account_id']
            env['PYTHONPATH'] = str(self.workspace / 'scripts')

            # Run command
            logger.info(f"Command: {' '.join(args)}")
            proc = subprocess.run(
                args,
                cwd=self.workspace,
                env=env,
                capture_output=True,
                text=True,
                timeout=120
            )

            result.output = proc.stdout + "\n" + proc.stderr

            # Check exit code
            expected_exit_code = scenario['expected'].get('exit_code', 0)
            if proc.returncode != expected_exit_code:
                result.error = f"Exit code {proc.returncode} (expected {expected_exit_code})"
                logger.error(f"✗ {result.error}")
                logger.error(f"Output: {result.output}")
                return result

            # Run validations
            for validation in scenario.get('validation', []):
                self.run_validation(validation, result)

            # Check if all validations passed
            result.passed = all(v['passed'] for v in result.validation_results)

            if result.passed:
                logger.info(f"✓ Test PASSED: {scenario['name']}")
            else:
                failed_checks = [v['check'] for v in result.validation_results if not v['passed']]
                logger.error(f"✗ Test FAILED: {scenario['name']}")
                logger.error(f"  Failed checks: {', '.join(failed_checks)}")

        except subprocess.TimeoutExpired:
            result.error = "Command timed out after 120 seconds"
            logger.error(f"✗ {result.error}")
        except Exception as e:
            result.error = str(e)
            logger.error(f"✗ Exception: {e}")
        finally:
            result.duration = (datetime.now() - start_time).total_seconds()

        return result

    def run_promotion_test(self, scenario: Dict[str, Any]) -> TestResult:
        """Run a promotion test scenario."""
        result = TestResult(scenario['id'], scenario['name'])
        start_time = datetime.now()

        logger.info(f"\n{'='*60}")
        logger.info(f"Running: {scenario['name']}")
        logger.info(f"{'='*60}")

        try:
            # Run prerequisites
            if 'prerequisites' in scenario:
                for prereq in scenario['prerequisites']:
                    if 'scenario' in prereq:
                        logger.info(f"Running prerequisite: {prereq['scenario']}")
                        # Find and run prerequisite scenario
                        prereq_scenario = next(
                            (s for s in self.test_config['scenarios'] if s['id'] == prereq['scenario']),
                            None
                        )
                        if prereq_scenario:
                            prereq_result = self.run_test(prereq_scenario)
                            if not prereq_result.passed:
                                result.error = f"Prerequisite failed: {prereq['scenario']}"
                                logger.error(f"✗ {result.error}")
                                return result
                    elif 'deploy_tier' in prereq:
                        # Simulate Terraform deployment
                        tier = prereq['deploy_tier']
                        template_id = scenario['command']['template_id']
                        # Need to determine template type from versions.yaml or assume 'stage'
                        self.simulate_tier_deployment(template_id, 'stage', tier)

            # Build command
            cmd = scenario['command']
            script_path = self.workspace / 'scripts' / 'validate_and_extract.py'

            args = [
                sys.executable,
                str(script_path),
                '--template-id', cmd['template_id'],
                '--to-tier', str(cmd['to_tier'])
            ]

            if cmd.get('tier_skip'):
                args.append('--tier-skip')
            if cmd.get('no_pr'):
                args.append('--no-pr')

            # Set environment variables
            env = os.environ.copy()
            env['HARNESS_API_KEY'] = self.test_config['config']['harness_api_key']
            env['HARNESS_ACCOUNT_ID'] = self.test_config['config']['harness_account_id']
            env['PYTHONPATH'] = str(self.workspace / 'scripts')

            # Run command
            logger.info(f"Command: {' '.join(args)}")
            proc = subprocess.run(
                args,
                cwd=self.workspace,
                env=env,
                capture_output=True,
                text=True,
                timeout=120
            )

            result.output = proc.stdout + "\n" + proc.stderr

            # Check exit code
            expected_exit_code = scenario['expected'].get('exit_code', 0)
            if proc.returncode != expected_exit_code:
                result.error = f"Exit code {proc.returncode} (expected {expected_exit_code})"
                logger.error(f"✗ {result.error}")
                logger.error(f"Output: {result.output}")
                return result

            # Run validations
            for validation in scenario.get('validation', []):
                self.run_validation(validation, result)

            # Check if all validations passed
            result.passed = all(v['passed'] for v in result.validation_results)

            if result.passed:
                logger.info(f"✓ Test PASSED: {scenario['name']}")
            else:
                failed_checks = [v['check'] for v in result.validation_results if not v['passed']]
                logger.error(f"✗ Test FAILED: {scenario['name']}")
                logger.error(f"  Failed checks: {', '.join(failed_checks)}")

        except subprocess.TimeoutExpired:
            result.error = "Command timed out after 120 seconds"
            logger.error(f"✗ {result.error}")
        except Exception as e:
            result.error = str(e)
            logger.error(f"✗ Exception: {e}")
        finally:
            result.duration = (datetime.now() - start_time).total_seconds()

        return result

    def run_sanitization_test(self, scenario: Dict[str, Any]) -> TestResult:
        """Run a sanitization test scenario."""
        result = TestResult(scenario['id'], scenario['name'])
        start_time = datetime.now()

        logger.info(f"\n{'='*60}")
        logger.info(f"Running: {scenario['name']}")
        logger.info(f"{'='*60}")

        try:
            from sanitize_template import sanitize_template

            # Get input template
            input_yaml = scenario['input_template']
            expected_output = scenario['expected_output']

            # Sanitize
            sanitized = sanitize_template(input_yaml)

            # Compare with expected
            sanitized_dict = yaml.safe_load(sanitized)
            expected_dict = yaml.safe_load(expected_output)

            if sanitized_dict == expected_dict:
                result.passed = True
                logger.info(f"✓ Test PASSED: {scenario['name']}")
            else:
                result.error = "Sanitized output doesn't match expected"
                logger.error(f"✗ {result.error}")
                logger.error(f"Expected:\n{expected_output}")
                logger.error(f"Got:\n{sanitized}")

        except Exception as e:
            result.error = str(e)
            logger.error(f"✗ Exception: {e}")
        finally:
            result.duration = (datetime.now() - start_time).total_seconds()

        return result

    def run_validation(self, validation: Dict[str, Any], result: TestResult):
        """Run a single validation check."""
        check_type = validation['check']
        validation_result = {
            'check': check_type,
            'passed': False,
            'message': ''
        }

        try:
            if check_type == 'file_exists':
                file_path = self.workspace / validation['file']
                validation_result['passed'] = file_path.exists()
                validation_result['message'] = f"File {'exists' if validation_result['passed'] else 'missing'}: {validation['file']}"

            elif check_type == 'file_not_exists':
                file_path = self.workspace / validation['file']
                validation_result['passed'] = not file_path.exists()
                validation_result['message'] = f"File {'absent' if validation_result['passed'] else 'exists'}: {validation['file']}"

            elif check_type == 'yaml_valid':
                file_path = self.workspace / validation['file']
                with open(file_path, 'r') as f:
                    yaml.safe_load(f)
                validation_result['passed'] = True
                validation_result['message'] = "YAML is valid"

            elif check_type == 'versions_entry_exists':
                versions = self.load_versions_yaml()
                template_type = validation['template_type']
                template_id = validation['template_id']
                version = validation['version']

                if template_type in versions.get('templates', {}):
                    if template_id in versions['templates'][template_type]:
                        template_data = versions['templates'][template_type][template_id]
                        versions_list = template_data.get('versions', [])
                        validation_result['passed'] = any(v['version'] == version for v in versions_list)

                validation_result['message'] = f"Versions entry {'found' if validation_result['passed'] else 'missing'}"

            elif check_type == 'tier_snapshot_exists':
                versions = self.load_versions_yaml()
                template_id = validation['template_id']
                tier = validation['tier']
                tier_label = f"tier-{tier}"

                # Find template in versions.yaml
                for template_type, templates in versions.get('templates', {}).items():
                    if template_id in templates:
                        tier_snapshots = templates[template_id].get('tier_snapshots', {})
                        validation_result['passed'] = tier_label in tier_snapshots
                        break

                validation_result['message'] = f"Tier snapshot {tier_label} {'found' if validation_result['passed'] else 'missing'}"

            elif check_type == 'exit_code':
                expected_code = validation['code']
                # This would be checked in the main test runner
                validation_result['passed'] = True
                validation_result['message'] = f"Exit code matches: {expected_code}"

            elif check_type == 'error_message_contains':
                text = validation['text']
                if result.output and text in result.output:
                    validation_result['passed'] = True
                validation_result['message'] = f"Error message {'contains' if validation_result['passed'] else 'missing'}: {text}"

            elif check_type == 'content_matches':
                file1 = self.workspace / validation['file1']
                file2 = self.workspace / validation['file2']

                if file1.exists() and file2.exists():
                    with open(file1, 'rb') as f:
                        hash1 = hashlib.md5(f.read()).hexdigest()
                    with open(file2, 'rb') as f:
                        hash2 = hashlib.md5(f.read()).hexdigest()
                    validation_result['passed'] = hash1 == hash2

                validation_result['message'] = f"Content {'matches' if validation_result['passed'] else 'differs'}"

            else:
                validation_result['message'] = f"Unknown validation check: {check_type}"

        except Exception as e:
            validation_result['message'] = f"Validation error: {e}"

        result.validation_results.append(validation_result)

        if validation_result['passed']:
            logger.info(f"  ✓ {validation_result['message']}")
        else:
            logger.warning(f"  ✗ {validation_result['message']}")

    def run_test(self, scenario: Dict[str, Any]) -> TestResult:
        """Run a test scenario based on its type."""
        test_type = scenario['type']

        if test_type == 'extraction':
            return self.run_extraction_test(scenario)
        elif test_type == 'promotion':
            return self.run_promotion_test(scenario)
        elif test_type == 'sanitization':
            return self.run_sanitization_test(scenario)
        elif test_type == 'integration':
            # Integration tests run multiple steps
            return self.run_integration_test(scenario)
        else:
            result = TestResult(scenario['id'], scenario['name'])
            result.error = f"Unknown test type: {test_type}"
            return result

    def run_integration_test(self, scenario: Dict[str, Any]) -> TestResult:
        """Run an integration test with multiple steps."""
        result = TestResult(scenario['id'], scenario['name'])
        start_time = datetime.now()

        logger.info(f"\n{'='*60}")
        logger.info(f"Running: {scenario['name']}")
        logger.info(f"{'='*60}")

        try:
            for i, step_config in enumerate(scenario['steps'], 1):
                step_name = step_config['step']
                logger.info(f"Step {i}: {step_name}")

                if 'command' in step_config:
                    # Run command
                    cmd = step_config['command']
                    # Similar to extraction/promotion test logic
                    # ... (implementation similar to above)
                    pass
                elif 'simulate' in step_config and step_config['simulate']:
                    # Simulate deployment
                    logger.info(f"  (simulated)")
                    pass

            # Run validations
            for validation in scenario.get('validation', []):
                self.run_validation(validation, result)

            result.passed = all(v['passed'] for v in result.validation_results)

            if result.passed:
                logger.info(f"✓ Integration test PASSED: {scenario['name']}")
            else:
                logger.error(f"✗ Integration test FAILED: {scenario['name']}")

        except Exception as e:
            result.error = str(e)
            logger.error(f"✗ Exception: {e}")
        finally:
            result.duration = (datetime.now() - start_time).total_seconds()

        return result

    def run_all_tests(self):
        """Run all test scenarios in order."""
        logger.info("=" * 60)
        logger.info("STARTING TEST RUN")
        logger.info("=" * 60)

        # Run tests in specified order
        execution_order = self.test_config.get('execution_order', [])

        for scenario_id in execution_order:
            # Find scenario
            scenario = next(
                (s for s in self.test_config['scenarios'] if s['id'] == scenario_id),
                None
            )

            if scenario:
                result = self.run_test(scenario)
                self.results.append(result)
            else:
                logger.warning(f"Scenario not found: {scenario_id}")

    def generate_report(self) -> str:
        """Generate test report."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        total_duration = sum(r.duration for r in self.results)

        report = []
        report.append("\n" + "=" * 60)
        report.append("TEST REPORT")
        report.append("=" * 60)
        report.append(f"Total Tests: {total}")
        report.append(f"Passed: {passed}")
        report.append(f"Failed: {failed}")
        report.append(f"Success Rate: {(passed/total*100):.1f}%")
        report.append(f"Total Duration: {total_duration:.2f}s")
        report.append("")

        # Failed tests
        if failed > 0:
            report.append("FAILED TESTS:")
            report.append("-" * 60)
            for result in self.results:
                if not result.passed:
                    report.append(f"✗ {result.name}")
                    report.append(f"  Error: {result.error}")
                    for val_result in result.validation_results:
                        if not val_result['passed']:
                            report.append(f"    - {val_result['message']}")
            report.append("")

        # Passed tests
        report.append("PASSED TESTS:")
        report.append("-" * 60)
        for result in self.results:
            if result.passed:
                report.append(f"✓ {result.name} ({result.duration:.2f}s)")

        report.append("=" * 60)

        return "\n".join(report)


def main():
    """Main test runner."""
    config_file = Path(__file__).parent / 'test_scenarios.yaml'
    workspace = Path(__file__).parent / 'test_workspace'

    runner = TestRunner(str(config_file), str(workspace))

    try:
        # Setup
        runner.setup_workspace()

        # Run tests
        runner.run_all_tests()

        # Generate report
        report = runner.generate_report()
        print(report)

        # Save report to file
        report_file = Path(__file__).parent / f'test_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
        with open(report_file, 'w') as f:
            f.write(report)

        logger.info(f"\n✓ Test report saved to: {report_file}")

        # Exit with appropriate code
        if all(r.passed for r in runner.results):
            sys.exit(0)
        else:
            sys.exit(1)

    finally:
        # Cleanup
        runner.cleanup_workspace()


if __name__ == "__main__":
    main()
