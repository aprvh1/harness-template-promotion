pipeline:
  identifier: ${identifier}
  name: ${name}
  description: ${description}
  orgIdentifier: ${org_id}
  projectIdentifier: ${project_id}
  stages:
    - stage:
        name: Test ${stage_template_ref} ${stage_version}
        identifier: test_stage
        template:
          templateRef: ${stage_template_ref}
          versionLabel: ${stage_version}
          templateInputs:
            type: Deployment
            spec:
              service:
                serviceRef: ${test_service}
              environment:
                environmentRef: dev
                deployToAll: false
            variables:
              - name: environment
                value: dev
              - name: service_name
                value: ${test_service}
  variables:
    - name: stage_version
      type: String
      value: ${stage_version}
    - name: test_service
      type: String
      value: ${test_service}
  tags:
    Purpose: Testing
    StageTemplateVersion: ${stage_version}
