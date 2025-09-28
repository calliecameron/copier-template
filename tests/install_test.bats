# shellcheck shell=bats

setup() {
    THIS_DIR="$(cd "$(dirname "${BATS_TEST_FILENAME}")" && pwd)"
    PROJECT_DIR="$(readlink -f "${THIS_DIR}/..")"

    bats_load_library 'bats-support'
    bats_load_library 'bats-assert'
}

run_copier() {
    REPO="${BATS_TEST_TMPDIR}/foo"
    mkdir "${REPO}"
    git init "${REPO}"
    uv run --directory "${REPO}" \
        copier copy --trust --vcs-ref=HEAD \
        "${@}" \
        "${PROJECT_DIR}" "${REPO}"
    # shellcheck disable=SC2164
    cd "${REPO}"
    git add --all
    make
    run git ls-files --others --exclude-standard
    assert_success
    refute_output
    git commit -m 'Foo bar'
}

@test "install no options" {
    run_copier \
        --data=project_name=Foo \
        --defaults
}

@test "install all options" {
    run_copier \
        --data=project_name=Foo \
        --data=project_version=0.0.0 \
        --data=author_name=Bar \
        --data=user_uses_bats=true \
        --data=is_python_package=true \
        --data=python_line_length=88 \
        --data=user_uses_pytest=true \
        --data=exports_requirements_txt=true \
        --data=user_has_javascript=true \
        --data=user_has_html=true \
        --data=user_has_css=true \
        --data=user_uses_github_actions=true \
        --data=github_repo=foo/bar
}
