pipeline:
  identifier: ${identifier}
  name: ${name}
  description: ${description}
  orgIdentifier: ${org_id}
  projectIdentifier: ${project_id}
  template:
    templateRef: ${pipeline_template_ref}
    versionLabel: ${template_version}
    templateInputs:
%{ for key, value in template_inputs ~}
      ${key}: ${value}
%{ endfor ~}
